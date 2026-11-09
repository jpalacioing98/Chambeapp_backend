"""Servicio de almacenamiento — MinIO (S3-compatible).

Este servicio gestiona la subida de archivos (imágenes, videos, documentos)
a MinIO, con optimización automática de imágenes usando Pillow.

Uso:
    from app.services.storage import upload_portfolio_image, upload_kyc

    # Subir imagen de portafolio (se optimiza a WebP)
    url = upload_portfolio_image(file_bytes, pds_id='42', filename='trabajo1')

    # Subir documento KYC
    url = upload_kyc(file_bytes, pds_id='42', filename='cedula.pdf')
"""

import os
import io
import json
import logging
from typing import Optional

try:
    import boto3
    from botocore.exceptions import ClientError, BotoCoreError
except ImportError:
    boto3 = None
    ClientError = Exception
    BotoCoreError = Exception

from PIL import Image

logger = logging.getLogger(__name__)


class StorageService:
    """Servicio de almacenamiento S3-compatible (MinIO)."""
    
    # Configuración desde variables de entorno
    S3_ENDPOINT = os.environ.get("S3_ENDPOINT", "http://localhost:9000")
    S3_ACCESS_KEY = os.environ.get("S3_ACCESS_KEY", "chambeapp")
    S3_SECRET_KEY = os.environ.get("S3_SECRET_KEY", "chambeapp_dev")
    S3_BUCKET = os.environ.get("S3_BUCKET", "chambeapp-portfolio")
    S3_REGION = os.environ.get("S3_REGION", "us-east-1")

    # Bucket PÚBLICO de avatares. Las fotos de perfil se muestran en
    # perfiles públicos, así que van en un bucket aparte con permiso de
    # SOLO lectura: el bucket principal guarda KYC y portafolios, que no
    # deben quedar expuestos. `S3_PUBLIC_ENDPOINT` es la URL que resuelve
    # en el NAVEGADOR (dentro del contenedor el host es `minio`).
    S3_PUBLIC_BUCKET = os.environ.get("S3_PUBLIC_BUCKET", "chambeapp-avatars")
    S3_PUBLIC_ENDPOINT = os.environ.get("S3_PUBLIC_ENDPOINT", "http://localhost:9000")

    # Bucket PÚBLICO de adjuntos del chat. Los archivos que comparten las
    # partes (fotos de la chamba, cotizaciones en PDF) se sirven desde aquí
    # con permiso de SOLO lectura; la URL usa el endpoint público.
    S3_CHAT_BUCKET = os.environ.get("S3_CHAT_BUCKET", "chambeapp-chat")
    
    # Límites de archivo
    MAX_IMAGE_SIZE = 10 * 1024 * 1024  # 10MB
    MAX_VIDEO_SIZE = 50 * 1024 * 1024  # 50MB
    MAX_DOC_SIZE = 10 * 1024 * 1024    # 10MB
    
    # Configuración de imagen
    IMAGE_MAX_DIMENSION = 800
    IMAGE_QUALITY = 85
    IMAGE_FORMAT = "WEBP"
    
    def __init__(self):
        """Inicializa el cliente S3."""
        self.client = boto3.client(
            "s3",
            endpoint_url=self.S3_ENDPOINT,
            aws_access_key_id=self.S3_ACCESS_KEY,
            aws_secret_access_key=self.S3_SECRET_KEY,
            region_name=self.S3_REGION
        )
        self._ensure_bucket()
        self._ensure_public_bucket()
        self._ensure_chat_bucket()
    
    def _ensure_bucket(self):
        """Crea el bucket si no existe."""
        try:
            self.client.head_bucket(Bucket=self.S3_BUCKET)
        except (ClientError, BotoCoreError):
            try:
                self.client.create_bucket(Bucket=self.S3_BUCKET)
                logger.info(f"Bucket '{self.S3_BUCKET}' creado")
            except (ClientError, BotoCoreError) as e:
                logger.error(f"Error creando bucket: {e}")

    def _ensure_public_bucket(self):
        """Crea el bucket público de avatares con permiso de SOLO lectura.

        El bucket principal sigue siendo privado (KYC, portafolios y
        documentos técnicos). Aquí solo viven las fotos de perfil, que por
        definición son públicas.
        """
        try:
            self.client.head_bucket(Bucket=self.S3_PUBLIC_BUCKET)
        except (ClientError, BotoCoreError):
            try:
                self.client.create_bucket(Bucket=self.S3_PUBLIC_BUCKET)
                logger.info(f"Bucket público '{self.S3_PUBLIC_BUCKET}' creado")
            except (ClientError, BotoCoreError) as e:
                logger.error(f"Error creando bucket público: {e}")
                return
        policy = {
            "Version": "2012-10-17",
            "Statement": [
                {
                    "Effect": "Allow",
                    "Principal": {"AWS": ["*"]},
                    "Action": ["s3:GetObject"],
                    "Resource": [f"arn:aws:s3:::{self.S3_PUBLIC_BUCKET}/*"],
                }
            ],
        }
        try:
            self.client.put_bucket_policy(
                Bucket=self.S3_PUBLIC_BUCKET, Policy=json.dumps(policy)
            )
        except (ClientError, BotoCoreError) as e:
            logger.error(f"Error aplicando política pública: {e}")
    
    def _ensure_chat_bucket(self):
        """Crea el bucket público de adjuntos del chat (SOLO lectura)."""
        try:
            self.client.head_bucket(Bucket=self.S3_CHAT_BUCKET)
        except (ClientError, BotoCoreError):
            try:
                self.client.create_bucket(Bucket=self.S3_CHAT_BUCKET)
                logger.info(f"Bucket público '{self.S3_CHAT_BUCKET}' creado")
            except (ClientError, BotoCoreError) as e:
                logger.error(f"Error creando bucket de chat: {e}")
                return
        policy = {
            "Version": "2012-10-17",
            "Statement": [
                {
                    "Effect": "Allow",
                    "Principal": {"AWS": ["*"]},
                    "Action": ["s3:GetObject"],
                    "Resource": [f"arn:aws:s3:::{self.S3_CHAT_BUCKET}/*"],
                }
            ],
        }
        try:
            self.client.put_bucket_policy(
                Bucket=self.S3_CHAT_BUCKET, Policy=json.dumps(policy)
            )
        except (ClientError, BotoCoreError) as e:
            logger.error(f"Error aplicando política pública del chat: {e}")

    def upload_chat_file(
        self, file_bytes: bytes, conversation_id: str, filename: str, content_type: str
    ) -> str:
        """Sube un adjunto del chat al bucket público y devuelve su URL.

        Args:
            file_bytes: Contenido del archivo
            conversation_id: Conversación (carpeta destino)
            filename: Nombre original del archivo
            content_type: Tipo MIME

        Returns:
            URL pública del archivo
        """
        if len(file_bytes) > self.MAX_DOC_SIZE:
            raise ValueError(f"Archivo excede {self.MAX_DOC_SIZE} bytes")

        key = f"chat/{conversation_id}/{filename}"
        self.client.put_object(
            Bucket=self.S3_CHAT_BUCKET,
            Key=key,
            Body=file_bytes,
            ContentType=content_type or "application/octet-stream",
        )
        return f"{self.S3_PUBLIC_ENDPOINT}/{self.S3_CHAT_BUCKET}/{key}"

    def upload_file(self, file_bytes: bytes, key: str, content_type: str) -> str:
        """Sube un archivo al bucket.
        
        Args:
            file_bytes: Contenido del archivo
            key: Ruta/clave en el bucket
            content_type: Tipo MIME
            
        Returns:
            URL pública del archivo
        """
        try:
            self.client.put_object(
                Bucket=self.S3_BUCKET,
                Key=key,
                Body=file_bytes,
                ContentType=content_type
            )
            return f"{self.S3_ENDPOINT}/{self.S3_BUCKET}/{key}"
        except ClientError as e:
            logger.error(f"Error subiendo archivo {key}: {e}")
            raise
    
    def upload_image(self, file_bytes: bytes, pds_id: str, filename: str) -> str:
        """Sube imagen optimizada (WebP) al portafolio.
        
        Args:
            file_bytes: Contenido de la imagen
            pds_id: ID del proveedor
            filename: Nombre del archivo
            
        Returns:
            URL de la imagen optimizada
        """
        if len(file_bytes) > self.MAX_IMAGE_SIZE:
            raise ValueError(f"Imagen excede {self.MAX_IMAGE_SIZE} bytes")
        
        # Optimizar imagen
        img = Image.open(io.BytesIO(file_bytes))
        
        # Convertir a RGB si es necesario
        if img.mode in ('RGBA', 'P'):
            img = img.convert('RGB')
        
        # Redimensionar manteniendo aspecto
        img.thumbnail(
            (self.IMAGE_MAX_DIMENSION, self.IMAGE_MAX_DIMENSION),
            Image.Resampling.LANCZOS
        )
        
        # Guardar como WebP
        buffer = io.BytesIO()
        img.save(buffer, format=self.IMAGE_FORMAT, quality=self.IMAGE_QUALITY)
        buffer.seek(0)
        
        key = f"portfolio/{pds_id}/{filename}.webp"
        return self.upload_file(
            buffer.getvalue(),
            key,
            content_type="image/webp"
        )

    def upload_avatar(self, file_bytes: bytes, user_id: str, filename: str) -> str:
        """Sube la foto de perfil (optimizada a WebP) del usuario.

        Args:
            file_bytes: Contenido de la imagen
            user_id: ID del usuario
            filename: Nombre del archivo original

        Returns:
            URL de la foto de perfil optimizada
        """
        if len(file_bytes) > self.MAX_IMAGE_SIZE:
            raise ValueError(f"Imagen excede {self.MAX_IMAGE_SIZE} bytes")

        # Optimizar imagen (mismo pipeline que upload_image)
        img = Image.open(io.BytesIO(file_bytes))
        if img.mode in ('RGBA', 'P'):
            img = img.convert('RGB')
        img.thumbnail(
            (self.IMAGE_MAX_DIMENSION, self.IMAGE_MAX_DIMENSION),
            Image.Resampling.LANCZOS
        )
        buffer = io.BytesIO()
        img.save(buffer, format=self.IMAGE_FORMAT, quality=self.IMAGE_QUALITY)
        buffer.seek(0)

        key = f"avatar/{user_id}/{filename}.webp"
        return self.upload_file(
            buffer.getvalue(),
            key,
            content_type="image/webp"
        )
    
    def upload_public_avatar(self, file_bytes: bytes, folder: str, filename: str) -> str:
        """Sube la foto de perfil al bucket PÚBLICO de avatares (optimizada a WebP).

        A diferencia de `upload_avatar` (bucket privado, para documentos
        técnicos), aquí el objeto es público por naturaleza y la URL devuelta
        usa `S3_PUBLIC_ENDPOINT`, que sí resuelve en el navegador.

        Args:
            file_bytes: Contenido de la imagen
            folder: Carpeta destino (p.ej. `42` o `sim/pds/001`)
            filename: Nombre base del archivo

        Returns:
            URL pública de la foto de perfil
        """
        if len(file_bytes) > self.MAX_IMAGE_SIZE:
            raise ValueError(f"Imagen excede {self.MAX_IMAGE_SIZE} bytes")

        img = Image.open(io.BytesIO(file_bytes))
        if img.mode in ('RGBA', 'P'):
            img = img.convert('RGB')
        img.thumbnail(
            (self.IMAGE_MAX_DIMENSION, self.IMAGE_MAX_DIMENSION),
            Image.Resampling.LANCZOS
        )
        buffer = io.BytesIO()
        img.save(buffer, format=self.IMAGE_FORMAT, quality=self.IMAGE_QUALITY)
        buffer.seek(0)

        key = f"avatar/{folder}/{filename}.webp"
        self.client.put_object(
            Bucket=self.S3_PUBLIC_BUCKET,
            Key=key,
            Body=buffer.getvalue(),
            ContentType="image/webp"
        )
        return f"{self.S3_PUBLIC_ENDPOINT}/{self.S3_PUBLIC_BUCKET}/{key}"

    def upload_video(self, file_bytes: bytes, pds_id: str, filename: str) -> str:
        """Sube video al portafolio.
        
        Args:
            file_bytes: Contenido del video
            pds_id: ID del proveedor
            filename: Nombre del archivo
            
        Returns:
            URL del video
        """
        if len(file_bytes) > self.MAX_VIDEO_SIZE:
            raise ValueError(f"Video excede {self.MAX_VIDEO_SIZE} bytes")
        
        key = f"portfolio/{pds_id}/{filename}"
        return self.upload_file(
            file_bytes,
            key,
            content_type="video/mp4"
        )
    
    def upload_document(self, file_bytes: bytes, pds_id: str, filename: str) -> str:
        """Sube documento (KYC, certificados) al bucket.
        
        Args:
            file_bytes: Contenido del documento
            pds_id: ID del proveedor
            filename: Nombre del archivo
            
        Returns:
            URL del documento
        """
        if len(file_bytes) > self.MAX_DOC_SIZE:
            raise ValueError(f"Documento excede {self.MAX_DOC_SIZE} bytes")
        
        key = f"kyc/{pds_id}/{filename}"
        return self.upload_file(
            file_bytes,
            key,
            content_type="application/pdf"
        )
    
    def delete_file(self, key: str):
        """Elimina un archivo del bucket.
        
        Args:
            key: Ruta/clave en el bucket
        """
        try:
            self.client.delete_object(Bucket=self.S3_BUCKET, Key=key)
        except ClientError as e:
            logger.error(f"Error eliminando archivo {key}: {e}")
            raise
    
    def get_presigned_url(self, key: str, expiration: int = 3600) -> str:
        """Genera URL prefirmada para acceso temporal.
        
        Args:
            key: Ruta/clave en el bucket
            expiration: Segundos de validez
            
        Returns:
            URL prefirmada
        """
        try:
            return self.client.generate_presigned_url(
                'get_object',
                Params={'Bucket': self.S3_BUCKET, 'Key': key},
                ExpiresIn=expiration
            )
        except ClientError as e:
            logger.error(f"Error generando URL prefirmada: {e}")
            raise


# Instancia singleton (solo si boto3 está disponible y el bucket es accesible).
# Se envuelve en try/except para no romper imports cuando MinIO no está
# disponible (p.ej. tests locales o arranque con servicio caído).
storage = None
if boto3 is not None:
    try:
        storage = StorageService()
    except Exception as e:  # noqa: BLE001
        logger.error(f"No se pudo inicializar StorageService: {e}")
        storage = None
