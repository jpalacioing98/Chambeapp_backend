"""Tests unitarios para Portfolio — Upload y gestión.

Estos tests verifican:
1. Subida de imagen (optimización WebP)
2. Subida de video
3. Subida de documento
4. Validación de tipos
5. Eliminación de archivos
6. Modelo PortfolioItem
"""

import io
import sys
import pytest
from unittest.mock import patch, MagicMock

try:
    from PIL import Image
    HAS_PIL = True
except ImportError:
    HAS_PIL = False

try:
    import boto3
    HAS_BOTO3 = True
except ImportError:
    HAS_BOTO3 = False

requires_boto3 = pytest.mark.skipif(not HAS_BOTO3, reason="requires boto3 (not installed)")
requires_pil = pytest.mark.skipif(not HAS_PIL, reason="requires Pillow (not installed)")

# Create a mock storage module so the portfolio blueprint can import it
# even when boto3 is not installed
if not HAS_BOTO3:
    _mock_storage_module = MagicMock()
    _mock_storage_module.storage = MagicMock()
    _mock_storage_module.StorageService = MagicMock
    sys.modules.setdefault('app.services.storage', _mock_storage_module)
    sys.modules.setdefault('boto3', MagicMock())
    sys.modules.setdefault('botocore', MagicMock())
    sys.modules.setdefault('botocore.exceptions', MagicMock())


@requires_boto3
class TestStorageService:
    """Tests para StorageService."""

    @pytest.fixture(autouse=True)
    def _mock_s3_client(self, monkeypatch):
        """Evita que boto3 resuelva credenciales vía IMDS (hang local)."""
        import boto3
        mock_client = MagicMock()
        monkeypatch.setattr(boto3, "client", lambda *args, **kwargs: mock_client)

    def test_upload_image_optimizes_webp(self):
        """upload_image debe optimizar a WebP."""
        from app.services.storage import StorageService
        
        # Crear imagen de prueba
        img = Image.new('RGB', (1000, 1000), color='red')
        buffer = io.BytesIO()
        img.save(buffer, format='PNG')
        file_bytes = buffer.getvalue()
        
        service = StorageService()
        
        with patch.object(service, 'upload_file') as mock_upload:
            mock_upload.return_value = "http://minio:9000/bucket/key.webp"
            
            url = service.upload_image(file_bytes, pds_id='42', filename='test')
            
            # Verificar que se llamó con WebP
            args, kwargs = mock_upload.call_args
            assert kwargs['content_type'] == 'image/webp'
            assert url == "http://minio:9000/bucket/key.webp"

    def test_upload_image_resizes(self):
        """upload_image debe redimensionar a máximo 800px."""
        from app.services.storage import StorageService
        
        # Crear imagen grande
        img = Image.new('RGB', (2000, 1500), color='blue')
        buffer = io.BytesIO()
        img.save(buffer, format='PNG')
        file_bytes = buffer.getvalue()
        
        service = StorageService()
        
        with patch.object(service, 'upload_file') as mock_upload:
            mock_upload.return_value = "http://minio:9000/bucket/key.webp"
            
            service.upload_image(file_bytes, pds_id='42', filename='test')
            
            # Verificar que la imagen subida es más pequeña
            args, kwargs = mock_upload.call_args
            uploaded_bytes = args[0]  # file_bytes es el primer arg
            
            uploaded_img = Image.open(io.BytesIO(uploaded_bytes))
            assert max(uploaded_img.size) <= 800

    def test_upload_video(self):
        """upload_video debe subir sin procesar."""
        from app.services.storage import StorageService
        
        service = StorageService()
        video_bytes = b"fake video content"
        
        with patch.object(service, 'upload_file') as mock_upload:
            mock_upload.return_value = "http://minio:9000/bucket/video.mp4"
            
            url = service.upload_video(video_bytes, pds_id='42', filename='test')
            
            args, kwargs = mock_upload.call_args
            assert kwargs['content_type'] == 'video/mp4'
            assert url == "http://minio:9000/bucket/video.mp4"

    def test_upload_document(self):
        """upload_document debe subir PDF."""
        from app.services.storage import StorageService
        
        service = StorageService()
        doc_bytes = b"%PDF-1.4 fake pdf"
        
        with patch.object(service, 'upload_file') as mock_upload:
            mock_upload.return_value = "http://minio:9000/bucket/doc.pdf"
            
            url = service.upload_document(doc_bytes, pds_id='42', filename='test')
            
            args, kwargs = mock_upload.call_args
            assert kwargs['content_type'] == 'application/pdf'

    def test_upload_image_too_large(self):
        """upload_image debe rechazar imágenes muy grandes."""
        from app.services.storage import StorageService
        
        service = StorageService()
        large_bytes = b"x" * (service.MAX_IMAGE_SIZE + 1)
        
        with pytest.raises(ValueError):
            service.upload_image(large_bytes, pds_id='42', filename='test')

    def test_delete_file(self):
        """delete_file debe llamar a S3 delete_object."""
        from app.services.storage import StorageService
        
        service = StorageService()
        
        with patch.object(service.client, 'delete_object') as mock_delete:
            service.delete_file('portfolio/42/test.webp')
            mock_delete.assert_called_once()


class TestPortfolioModel:
    """Tests para el modelo PortfolioItem."""

    def test_to_dict(self):
        """to_dict debe retornar dict con campos esperados."""
        from app.models.portfolio import PortfolioItem
        
        item = PortfolioItem(
            pds_id=42,
            titulo='Test',
            tipo='foto',
            categoria='plomeria',
            s3_key='portfolio/42/test.webp',
            url='http://minio:9000/bucket/portfolio/42/test.webp',
            estado='pendiente_revision'
        )
        
        data = item.to_dict()
        assert data['pds_id'] == 42
        assert data['titulo'] == 'Test'
        assert data['tipo'] == 'foto'
        assert data['estado'] == 'pendiente_revision'

    def test_approve(self):
        """approve debe cambiar estado a 'aprobado'."""
        from app.models.portfolio import PortfolioItem
        
        item = PortfolioItem(
            pds_id=42,
            titulo='Test',
            tipo='foto',
            categoria='plomeria',
            s3_key='portfolio/42/test.webp',
            url='http://minio:9000/bucket/portfolio/42/test.webp'
        )
        
        with patch('app.models.portfolio.db.session.commit'):
            item.approve(admin_id=1)
            assert item.estado == 'aprobado'
            assert item.verificado_por == 1

    def test_increment_views(self):
        """increment_views debe incrementar contador."""
        from app.models.portfolio import PortfolioItem
        
        item = PortfolioItem(
            pds_id=42,
            titulo='Test',
            tipo='foto',
            categoria='plomeria',
            s3_key='portfolio/42/test.webp',
            url='http://minio:9000/bucket/portfolio/42/test.webp'
        )
        item.vistas = 0
        
        with patch('app.models.portfolio.db.session.commit'):
            item.increment_views()
            assert item.vistas == 1


class TestPortfolioBlueprint:
    """Tests para los endpoints de portafolio."""

    @pytest.fixture
    def app(self):
        from app import create_app
        from app.extensions import db as _db
        app = create_app("app.config.TestingConfig")
        with app.app_context():
            _db.create_all()
            yield app
            _db.session.remove()
            _db.drop_all()

    @pytest.fixture
    def client(self, app):
        return app.test_client()

    @pytest.fixture
    def auth_headers(self, client):
        """Registra un PDS y retorna headers de autenticación."""
        client.post(
            "/api/v1/auth/register",
            json={
                "email": "pds_portfolio@test.com",
                "password": "secret123",
                "rol": "pds",
                "acepto_tyc": True,
                "ip": "127.0.0.1",
            },
        )
        resp = client.post(
            "/api/v1/auth/login",
            json={"email": "pds_portfolio@test.com", "password": "secret123"},
        )
        token = resp.get_json()["access_token"]
        return {"Authorization": f"Bearer {token}"}

    def test_upload_requires_file(self, client, auth_headers):
        """POST /upload debe requerir archivo."""
        from app import create_app
        
        # Mock storage
        with patch('app.services.storage.storage.upload_image') as mock_upload:
            mock_upload.return_value = "http://minio:9000/test.webp"
            
            # Sin archivo
            response = client.post(
                '/api/v1/portfolio/upload',
                headers=auth_headers,
                data={
                    'titulo': 'Test',
                    'tipo': 'foto',
                    'categoria': 'plomeria'
                }
            )
            assert response.status_code == 400

    def test_upload_invalid_type(self, client, auth_headers):
        """POST /upload debe rechazar tipo inválido."""
        from app import create_app
        
        with patch('app.services.storage.storage.upload_image') as mock_upload:
            mock_upload.return_value = "http://minio:9000/test.webp"
            
            # Crear archivo fake
            data = {
                'archivo': (io.BytesIO(b"fake"), 'test.png'),
                'titulo': 'Test',
                'tipo': 'invalid',
                'categoria': 'plomeria'
            }
            
            response = client.post(
                '/api/v1/portfolio/upload',
                headers=auth_headers,
                data=data,
                content_type='multipart/form-data'
            )
            assert response.status_code == 400

    def test_upload_success(self, client, auth_headers):
        """POST /upload debe subir exitosamente."""
        from app import create_app
        
        with patch('app.services.storage.storage.upload_image') as mock_upload:
            mock_upload.return_value = "http://minio:9000/test.webp"
            
            data = {
                'archivo': (io.BytesIO(b"fake image"), 'test.png'),
                'titulo': 'Reparación tubería',
                'tipo': 'foto',
                'categoria': 'plomeria',
                'descripcion': 'Trabajo realizado'
            }
            
            response = client.post(
                '/api/v1/portfolio/upload',
                headers=auth_headers,
                data=data,
                content_type='multipart/form-data'
            )
            
            assert response.status_code == 201
            assert response.json['titulo'] == 'Reparación tubería'
            assert response.json['url'] == 'http://minio:9000/test.webp'
