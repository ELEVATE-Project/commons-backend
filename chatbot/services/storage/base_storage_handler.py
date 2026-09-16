"""
Base storage handler interface for cloud storage operations
"""
from abc import ABC, abstractmethod
from typing import Dict, Optional, BinaryIO
from dataclasses import dataclass
import requests


@dataclass
class UploadConfig:
    """Configuration for file upload operations"""
    file_name: str
    file_type: str
    folder_structure: Optional[str] = None
    entity_id: Optional[str] = None
    acl: str | None = None
    expires_in: int = 3600
    metadata: Optional[Dict[str, str]] = None


@dataclass
class UploadResult:
    """Result of an upload operation"""
    upload_url: str
    object_key: str
    public_url: str
    object_url: str
    success: bool = True
    error: Optional[str] = None


class BaseStorageHandler(ABC):
    """
    Abstract base class for storage handlers.
    Defines the interface that all storage providers must implement.
    """

    def __init__(self, config: Dict):
        """
        Initialize storage handler with configuration
        
        Args:
            config: Dictionary containing provider-specific configuration
        """
        self.config = config

    @abstractmethod
    def generate_presigned_url(self, upload_config: UploadConfig) -> UploadResult:
        """
        Generate a presigned URL for uploading a file
        
        Args:
            upload_config: Configuration for the upload operation
            
        Returns:
            UploadResult containing upload URL and object details
        """
        pass

    @abstractmethod
    def upload_file(self, file_obj: BinaryIO, upload_config: UploadConfig) -> UploadResult:
        """
        Directly upload a file to storage
        
        Args:
            file_obj: File object to upload
            upload_config: Configuration for the upload operation
            
        Returns:
            UploadResult containing upload details
        """
        pass

    @abstractmethod
    def delete_file(self, object_key: str) -> bool:
        """
        Delete a file from storage
        
        Args:
            object_key: Key/path of the object to delete
            
        Returns:
            True if deletion was successful, False otherwise
        """
        pass

    @abstractmethod
    def get_public_url(self, object_key: str) -> str:
        """
        Get the public URL for accessing a file
        
        Args:
            object_key: Key/path of the object
            
        Returns:
            Public URL string
        """
        pass

    @abstractmethod
    def file_exists(self, object_key: str) -> bool:
        """
        Check if a file exists in storage
        
        Args:
            object_key: Key/path of the object
            
        Returns:
            True if file exists, False otherwise
        """
        pass

    def _generate_object_key(self, upload_config: UploadConfig) -> str:
        """
        Generate object key for the file.
        
        Args:
            upload_config: Upload configuration
            
        Returns:
            Generated object key with format: folder/entity_id/filename
        """
        folder = upload_config.folder_structure or ''
        entity_part = f"{upload_config.entity_id}/" if upload_config.entity_id else ''
        return f"{folder}{entity_part}{upload_config.file_name}"

    def get_file_from_store(self, object_url: str) -> any:
        """
        Get a file from storage
        
        Args:
            object_url: URL of the object to get
            
        Returns:
            File object
        """
        response = requests.get(object_url)
        response.raise_for_status()
        return response.content
