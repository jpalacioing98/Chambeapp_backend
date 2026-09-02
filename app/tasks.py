"""Celery application and tasks for background jobs."""

import os
from celery import Celery
from celery.schedules import crontab

# Create Celery app
celery_app = Celery(
    "chambeapp",
    broker=os.getenv("REDIS_URL", "redis://localhost:6379/0"),
    backend=os.getenv("REDIS_URL", "redis://localhost:6379/0"),
)

# Configure Celery
celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="America/Bogota",
    enable_utc=True,
    task_track_started=True,
    task_time_limit=300,  # 5 minutes max per task
    task_soft_time_limit=240,  # 4 minutes soft limit
    worker_prefetch_multiplier=1,
    worker_max_tasks_per_child=100,
)

# Schedule periodic tasks
celery_app.conf.beat_schedule = {
    # Auto-release payments after 48 hours
    "auto-release-payments": {
        "task": "app.tasks.auto_release_payments",
        "schedule": crontab(minute="*/30"),  # Every 30 minutes
    },
    # Auto-approve milestones after 48 hours
    "auto-approve-milestones": {
        "task": "app.tasks.auto_approve_milestones",
        "schedule": crontab(minute="*/30"),  # Every 30 minutes
    },
    # Clean expired coins every 24 hours
    "clean-expired-coins": {
        "task": "app.tasks.clean_expired_coins",
        "schedule": crontab(hour=0, minute=0),  # Daily at midnight
    },
    # Send SLA alerts for KYC verification
    "kyc-sla-alerts": {
        "task": "app.tasks.check_kyc_sla",
        "schedule": crontab(minute="*/60"),  # Every hour
    },
}


# Import tasks after creating app
@celery_app.task(name="app.tasks.auto_release_payments")
def auto_release_payments():
    """Auto-release payments after 48 hours of contract completion."""
    from app import create_app
    from app.extensions import db
    from app.models.contract import Contract, EstadoContrato
    from app.models.payment import Payment, EstadoPago
    from datetime import datetime, timedelta, timezone
    
    app = create_app()
    with app.app_context():
        # Find contracts completed more than 48 hours ago
        cutoff = datetime.now(timezone.utc) - timedelta(hours=48)
        
        contracts = Contract.query.filter(
            Contract.estado == EstadoContrato.COMPLETADO,
            Contract.fin_en < cutoff,
        ).all()
        
        released_count = 0
        for contract in contracts:
            # Find pending payment for this contract
            payment = Payment.query.filter_by(
                contract_id=contract.id,
                estado=EstadoPago.PENDIENTE,
            ).first()
            
            if payment:
                # Auto-release the payment
                payment.estado = EstadoPago.LIBERADO
                payment.liberado_en = datetime.now(timezone.utc)
                db.session.commit()
                released_count += 1
        
        return f"Auto-released {released_count} payments"


@celery_app.task(name="app.tasks.auto_approve_milestones")
def auto_approve_milestones():
    """Auto-approve milestones after 48 hours of creation."""
    from app import create_app
    from app.extensions import db
    from app.models.modalidad import Milestone, EstadoHito
    from datetime import datetime, timedelta, timezone
    
    app = create_app()
    with app.app_context():
        # Find pending milestones created more than 48 hours ago
        cutoff = datetime.now(timezone.utc) - timedelta(hours=48)
        
        milestones = Milestone.query.filter(
            Milestone.estado == EstadoHito.PENDIENTE,
            Milestone.created_at < cutoff,
        ).all()
        
        approved_count = 0
        for milestone in milestones:
            milestone.estado = EstadoHito.APROBADO
            milestone.aprobado_en = datetime.now(timezone.utc)
            approved_count += 1
        
        db.session.commit()
        return f"Auto-approved {approved_count} milestones"


@celery_app.task(name="app.tasks.clean_expired_coins")
def clean_expired_coins():
    """Clean expired promotional coins."""
    from app import create_app
    from app.extensions import db
    from app.services.wallet import limpiar_monedas_vencidas
    
    app = create_app()
    with app.app_context():
        cleaned = limpiar_monedas_vencidas()
        return f"Cleaned {cleaned} expired coin entries"


@celery_app.task(name="app.tasks.check_kyc_sla")
def check_kyc_sla():
    """Check KYC verification SLA (48 hours)."""
    from app import create_app
    from app.extensions import db
    from app.models.kyc import KycDocument, KycStatus
    from datetime import datetime, timedelta, timezone
    
    app = create_app()
    with app.app_context():
        # Find documents pending for more than 48 hours
        cutoff = datetime.now(timezone.utc) - timedelta(hours=48)
        
        pending_docs = KycDocument.query.filter(
            KycDocument.estado == KycStatus.PENDIENTE,
            KycDocument.created_at < cutoff,
        ).all()
        
        if pending_docs:
            # TODO: Send alert to admin
            # send_admin_alert(f"KYC SLA: {len(pending_docs)} documents pending for >48h")
            pass
        
        return f"KYC SLA check: {len(pending_docs)} documents pending"
