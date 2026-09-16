"""Script de migración: KYC base64 → MinIO.

Este script migra los documentos KYC almacenados como base64 en la
base de datos a MinIO (S3-compatible), actualizando el campo
archivo_url y limpiando archivo_base64.

Uso:
    cd Chambeapp_backend
    python migrations/scripts/migrate_kyc.py
"""

import base64
import logging

from app import create_app
from app.extensions import db
from app.models.kyc import DocumentoUsuario
from app.services.storage import storage

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def migrate():
    """Migra documentos KYC de base64 a MinIO."""
    app = create_app()
    
    with app.app_context():
        # Obtener documentos con base64
        docs = DocumentoUsuario.query.filter(
            DocumentoUsuario.archivo_base64.isnot(None)
        ).all()
        
        logger.info(f"Encontrados {len(docs)} documentos KYC con base64")
        
        migrated = 0
        errors = 0
        
        for doc in docs:
            try:
                # Decodificar base64
                file_bytes = base64.b64decode(doc.archivo_base64)
                
                # Determinar extensión
                ext = 'pdf'
                if doc.nombre_documento and '.' in doc.nombre_documento:
                    ext = doc.nombre_documento.split('.')[-1]
                
                # Subir a MinIO
                url = storage.upload_document(
                    file_bytes,
                    str(doc.usuario_id),
                    f"{doc.id}.{ext}"
                )
                
                # Actualizar DB
                doc.archivo_url = url
                doc.archivo_base64 = None
                
                migrated += 1
                logger.info(f"✅ Migrado doc {doc.id} → {url}")
                
            except Exception as e:
                errors += 1
                logger.error(f"❌ Error migrando doc {doc.id}: {e}")
        
        # Commit cambios
        db.session.commit()
        
        logger.info(f"🎉 Migración completada: {migrated} exitosos, {errors} errores")


if __name__ == "__main__":
    migrate()
