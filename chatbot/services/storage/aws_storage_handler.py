"""
AWS S3 storage handler implementation
"""
import os
import logging
import boto3
from botocore.exceptions import ClientError
from typing import BinaryIO
from urllib.parse import urlparse
from .base_storage_handler import BaseStorageHandler, UploadConfig, UploadResult

logger = logging.getLogger('django')


class AWSS3StorageHandler(BaseStorageHandler):
    """
    AWS S3 implementation of the storage handler
    Handles file uploads, deletions, and URL generation for S3
    """

    def __init__(self, config: dict):
        """
        Initialize AWS S3 storage handler
        
        Args:
            config: Dictionary containing S3 configuration
                   Expected keys: bucket_name, region_name
        """
        super().__init__(config)
        self.bucket_name = config.get('bucket_name') or os.getenv('S3_BUCKET_NAME')
        self.region_name = config.get('region_name') or os.getenv('AWS_REGION')
        self.access_key = os.getenv('AWS_ACCESS_KEY_ID')
        self.secret_key = os.getenv('AWS_SECRET_ACCESS_KEY')
        
        if not all([self.bucket_name, self.region_name]):
            raise ValueError("AWS S3 configuration incomplete: bucket_name and region_name are required")
        
        self._client = None

    @property
    def client(self):
        """Lazy initialization of S3 client"""
        if self._client is None:
            self._client = boto3.client(
                's3',
                region_name=self.region_name,
                aws_access_key_id=self.access_key,
                aws_secret_access_key=self.secret_key
            )
        return self._client

    def generate_presigned_url(self, upload_config: UploadConfig) -> UploadResult:
        """
        Generate a presigned URL for S3 upload
        
        Args:
            upload_config: Configuration for the upload operation
            
        Returns:
            UploadResult with presigned URL and object details
        """
        try:
            object_key = self._generate_object_key(upload_config)
            
            params = {
                'Bucket': self.bucket_name,
                'Key': object_key,
                'ContentType': upload_config.file_type,
            }
            
            # Add ACL if specified
            if upload_config.acl:
                params['ACL'] = upload_config.acl
            
            # Add metadata if provided
            if upload_config.metadata:
                params['Metadata'] = upload_config.metadata
            
            upload_url = self.client.generate_presigned_url(
                'put_object',
                Params=params,
                ExpiresIn=upload_config.expires_in
            )
            
            public_url = self.get_public_url(object_key)
            s3_url = self.get_s3_url(object_key)
            
            logger.info(f"Generated presigned URL for S3: {object_key}")
            
            return UploadResult(
                upload_url=upload_url,
                object_key=object_key,
                public_url=public_url,
                object_url=s3_url,
                success=True
            )
            
        except ClientError as e:
            error_msg = f"Failed to generate presigned URL: {str(e)}"
            logger.error(error_msg)
            return UploadResult(
                upload_url='',
                object_key='',
                public_url='',
                object_url='',
                success=False,
                error=error_msg
            )

    def upload_file(self, file_obj: BinaryIO, upload_config: UploadConfig) -> UploadResult:
        """
        Directly upload a file to S3
        
        Args:
            file_obj: File object to upload
            upload_config: Configuration for the upload
            
        Returns:
            UploadResult with upload details
        """
        try:
            object_key = self._generate_object_key(upload_config)
            
            extra_args = {
                'ContentType': upload_config.file_type,
            }
            
            if upload_config.acl:
                extra_args['ACL'] = upload_config.acl
            
            if upload_config.metadata:
                extra_args['Metadata'] = upload_config.metadata
            
            self.client.upload_fileobj(
                file_obj,
                self.bucket_name,
                object_key,
                ExtraArgs=extra_args
            )
            
            public_url = self.get_public_url(object_key)
            s3_url = self.get_s3_url(object_key)

            logger.info(f"Successfully uploaded file to S3: {object_key}")
            
            return UploadResult(
                upload_url='',
                object_key=object_key,
                public_url=public_url,
                object_url=s3_url,
                success=True
            )
            
        except ClientError as e:
            error_msg = f"Failed to upload file to S3: {str(e)}"
            logger.error(error_msg)
            return UploadResult(
                upload_url='',
                object_key='',
                public_url='',
                object_url='',
                success=False,
                error=error_msg
            )

    def delete_file(self, object_key: str) -> bool:
        """
        Delete a file from S3
        
        Args:
            object_key: S3 object key to delete
            
        Returns:
            True if deletion was successful
        """
        try:
            self.client.delete_object(
                Bucket=self.bucket_name,
                Key=object_key
            )
            logger.info(f"Successfully deleted file from S3: {object_key}")
            return True
            
        except ClientError as e:
            logger.error(f"Failed to delete file from S3: {str(e)}")
            return False

    def get_public_url(self, object_key: str) -> str:
        """
        Get the public URL for an S3 object
        
        Args:
            object_key: S3 object key
            
        Returns:
            Public URL string
        """
        return f"https://{self.bucket_name}/{object_key}"

    def get_s3_url(self, object_key: str) -> str:
        """
        Get the s3 URL for an S3 object
        
        Args:
            object_key: S3 object key
            
        Returns:
            s3 URL string
        """
        return f"s3://{self.bucket_name}/{object_key}"

    def file_exists(self, object_key: str) -> bool:
        """
        Check if a file exists in S3
        
        Args:
            object_key: S3 object key
            
        Returns:
            True if file exists
        """
        try:
            self.client.head_object(
                Bucket=self.bucket_name,
                Key=object_key
            )
            return True
        except ClientError:
            return False

    def get_file_from_store(self, object_url: str) -> any:
        """
        Get a file from S3
        
        Args:
            object_url: S3 object URL
            
        Returns:
            File object
        """
        bucket_name = os.environ.get('S3_BUCKET_NAME')
        parsed = urlparse(object_url)
        object_key = parsed.path.lstrip("/")
        return self.client.get_object(Bucket=bucket_name, Key=object_key).get('Body').read()