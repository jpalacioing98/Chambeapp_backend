"""Portfolio blueprint — Upload y gestión de portafolio.

Endpoints:
    POST /api/v1/portfolio/upload  → Sube un item al portafolio
    GET  /api/v1/portfolio/items   → Lista items del usuario
    GET  /api/v1/portfolio/<id>    → Obtiene un item
    DELETE /api/v1/portfolio/<id>  → Elimina un item
"""

from flask import request, jsonify
from flask.views import MethodView
from flask_smorest import Blueprint, abort
from flask_jwt_extended import jwt_required, get_jwt_identity

from app.extensions import db
from app.models.portfolio import PortfolioItem
from app.services.storage import storage

blp = Blueprint("portfolio", __name__, description="Gestión de portafolio")


@blp.route("/upload")
class PortfolioUpload(MethodView):
    @jwt_required()
    @blp.doc(security=[{"Bearer": []}], summary="Sube un item al portafolio")
    def post(self):
        """Sube un item (foto/video/documento) al portafolio del proveedor.
        
        Form data:
            archivo: File (requerido)
            titulo: String (requerido)
            tipo: 'foto' | 'video' | 'documento' (requerido)
            categoria: String (requerido)
            descripcion: String (opcional)
        """
        user_id = int(get_jwt_identity())
        
        # Validar archivo
        file = request.files.get('archivo')
        if not file:
            abort(400, message="Archivo requerido")
        
        # Validar campos
        titulo = request.form.get('titulo', '').strip()
        tipo = request.form.get('tipo', '').strip()
        categoria = request.form.get('categoria', '').strip()
        descripcion = request.form.get('descripcion', '').strip()
        precio_raw = request.form.get('precio', '').strip()
        try:
            precio = int(float(precio_raw)) if precio_raw else None
        except ValueError:
            precio = None
        
        if not titulo:
            abort(400, message="Título requerido")
        
        if tipo not in ('foto', 'video', 'documento'):
            abort(400, message="Tipo inválido: debe ser 'foto', 'video' o 'documento'")
        
        if not categoria:
            abort(400, message="Categoría requerida")
        
        # Leer bytes del archivo
        file_bytes = file.read()
        if not file_bytes:
            abort(400, message="Archivo vacío")
        
        # Subir según tipo (portada)
        try:
            if tipo == 'foto':
                url = storage.upload_portfolio_image(file_bytes, str(user_id), file.filename or 'image')
            elif tipo == 'video':
                url = storage.upload_video(file_bytes, str(user_id), file.filename or 'video')
            else:
                url = storage.upload_document(file_bytes, str(user_id), file.filename or 'doc')
        except ValueError as e:
            abort(400, message=str(e))
        except Exception as e:
            abort(500, message=f"Error subiendo archivo: {str(e)}")

        # Galería opcional: antes / después / normales.
        def subir_lista(campo: str) -> list[str]:
            urls: list[str] = []
            for extra in request.files.getlist(campo):
                if extra is None:
                    continue
                data = extra.read()
                if not data:
                    continue
                try:
                    urls.append(
                        storage.upload_portfolio_image(
                            data, str(user_id), extra.filename or campo
                        )
                    )
                except Exception:
                    continue
            return urls

        antes = subir_lista('antes')
        despues = subir_lista('despues')
        galeria = subir_lista('galeria')

        # Crear registro
        item = PortfolioItem(
            pds_id=user_id,
            titulo=titulo,
            descripcion=descripcion,
            tipo=tipo,
            categoria=categoria,
            precio=precio,
            s3_key=(
                storage.key_from_url(url, storage.S3_PORTFOLIO_BUCKET)
                or f"portfolio/{user_id}/{file.filename}"
            ),
            url=url,
            antes=antes,
            despues=despues,
            galeria=galeria,
            file_size_bytes=len(file_bytes),
            mime_type=file.content_type
        )
        db.session.add(item)
        db.session.commit()
        
        return {
            "id": item.id,
            "titulo": item.titulo,
            "tipo": item.tipo,
            "categoria": item.categoria,
            "url": item.url,
            "estado": item.estado
        }, 201


@blp.route("/items")
class PortfolioItems(MethodView):
    @jwt_required()
    @blp.doc(security=[{"Bearer": []}], summary="Lista items del portafolio")
    def get(self):
        """Lista todos los items del portafolio del usuario autenticado."""
        user_id = int(get_jwt_identity())
        items = PortfolioItem.query.filter_by(pds_id=user_id).all()
        
        return [item.to_dict() for item in items]


@blp.route("/<int:item_id>")
class PortfolioItemDetail(MethodView):
    @jwt_required()
    @blp.doc(security=[{"Bearer": []}], summary="Obtiene un item del portafolio")
    def get(self, item_id):
        """Obtiene un item específico del portafolio."""
        user_id = int(get_jwt_identity())
        item = PortfolioItem.query.get_or_404(item_id)
        
        if item.pds_id != user_id:
            abort(403, message="No tienes permiso para ver este item")
        
        return item.to_dict()
    
    @jwt_required()
    @blp.doc(security=[{"Bearer": []}], summary="Elimina un item del portafolio")
    def delete(self, item_id):
        """Elimina un item del portafolio."""
        user_id = int(get_jwt_identity())
        item = PortfolioItem.query.get_or_404(item_id)
        
        if item.pds_id != user_id:
            abort(403, message="No tienes permiso para eliminar este item")
        
        # Eliminar de MinIO (bucket público nuevo o privado heredado)
        try:
            key_publico = storage.key_from_url(
                item.url or "", storage.S3_PORTFOLIO_BUCKET
            )
            if key_publico:
                storage.delete_file(key_publico, bucket=storage.S3_PORTFOLIO_BUCKET)
            elif item.s3_key:
                storage.delete_file(item.s3_key)
        except Exception as e:
            abort(500, message=f"Error eliminando archivo: {str(e)}")
        
        db.session.delete(item)
        db.session.commit()
        
        return "", 204


@blp.route("/importar-ultima-chamba")
class PortfolioImportLastChamba(MethodView):
    """Monta la última chamba finalizada (con su foto de evidencia) en el
    portafolio del PDS, sin volver a subir el archivo."""

    @jwt_required()
    def post(self):
        user_id = int(get_jwt_identity())

        from app.models.chamba import Chamba, EstadoChamba
        from app.models.contract import Contract

        chamba = (
            db.session.query(Chamba)
            .join(Contract, Contract.id == Chamba.contract_id)
            .filter(
                Contract.proveedor_id == user_id,
                Chamba.estado == EstadoChamba.FINALIZADA,
            )
            .order_by(Chamba.fecha_finalizacion.desc(), Chamba.id.desc())
            .first()
        )
        if chamba is None:
            abort(404, message="No tienes chambas finalizadas para importar.")

        urls = list(chamba.evidencia_salida or []) + list(
            chamba.evidencia_entrada or []
        )
        if not urls:
            abort(400, message="La última chamba no tiene fotos de evidencia.")

        url = urls[0]
        existente = PortfolioItem.query.filter_by(
            pds_id=user_id, url=url
        ).first()
        if existente is not None:
            return existente.to_dict(), 200

        entrada = [u for u in (chamba.evidencia_entrada or []) if u]
        salida = [u for u in (chamba.evidencia_salida or []) if u]
        cover = (salida or entrada)[0]

        service = chamba.contract.service if chamba.contract else None
        from app.models.user import User

        autor = (
            db.session.get(User, chamba.contract.solicitante_id)
            if chamba.contract
            else None
        )
        item = PortfolioItem(
            pds_id=user_id,
            titulo=(service.titulo if service else f"Chamba #{chamba.id}")[:100],
            descripcion=service.descripcion if service else None,
            tipo="foto",
            categoria=(service.categoria if service else "general")[:50],
            precio=(service.presupuesto if service else None),
            calificacion=chamba.rating_estrellas,
            resena_texto=chamba.rating_comentario,
            resena_autor=(
                (autor.nombre or autor.email) if autor is not None else None
            ),
            estado="aprobado",
            s3_key=f"chamba/{chamba.id}/{cover.rsplit('/', 1)[-1]}",
            url=cover,
            antes=entrada,
            despues=salida,
            galeria=[],
            mime_type="image/jpeg",
        )
        db.session.add(item)
        db.session.commit()

        return item.to_dict(), 201


@blp.route("/pds/<int:pds_id>")
class PortfolioByPDS(MethodView):
    @blp.doc(summary="Obtiene portafolio público de un proveedor")
    def get(self, pds_id):
        """Obtiene items aprobados del portafolio de un proveedor (público)."""
        items = PortfolioItem.get_approved_by_pds(pds_id)
        
        return [{
            'id': i.id,
            'titulo': i.titulo,
            'tipo': i.tipo,
            'categoria': i.categoria,
            'url': i.url,
            'vistas': i.vistas,
        } for i in items]
