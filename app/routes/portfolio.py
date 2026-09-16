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
        
        # Subir según tipo
        try:
            if tipo == 'foto':
                url = storage.upload_image(file_bytes, str(user_id), file.filename or 'image')
            elif tipo == 'video':
                url = storage.upload_video(file_bytes, str(user_id), file.filename or 'video')
            else:
                url = storage.upload_document(file_bytes, str(user_id), file.filename or 'doc')
        except ValueError as e:
            abort(400, message=str(e))
        except Exception as e:
            abort(500, message=f"Error subiendo archivo: {str(e)}")
        
        # Crear registro
        item = PortfolioItem(
            pds_id=user_id,
            titulo=titulo,
            descripcion=descripcion,
            tipo=tipo,
            categoria=categoria,
            s3_key=f"portfolio/{user_id}/{file.filename}",
            url=url,
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
        
        # Eliminar de MinIO
        try:
            storage.delete_file(item.s3_key)
        except Exception as e:
            abort(500, message=f"Error eliminando archivo: {str(e)}")
        
        db.session.delete(item)
        db.session.commit()
        
        return "", 204


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
