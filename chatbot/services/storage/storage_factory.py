"""
Storage Factory - Factory pattern for creating storage handlers based on cloud provider
"""
import os
import logging
from typing import Optional, Dict

from .base_storage_handler import BaseStorageHandler
from .aws_storage_handler import AWSS3StorageHandler
from .local_storage_handler import LocalStorageHandler

logger = logging.getLogger('django')


class StorageFactory:
    """
    Factory class for creating storage handler instances based on cloud provider.
    Supports multiple cloud providers through a unified interface.
    """
    
    # Registry of available storage handlers
    _handlers = {
        'AWS': AWSS3StorageHandler,
        'LOCAL': LocalStorageHandler,
        # Add more providers here in the future:
        # 'GCP': GCPStorageHandler,
        # 'AZURE': AzureStorageHandler,
    }
    
    @classmethod
    def get_storage_handler(cls, provider: Optional[str] = None, config: Optional[Dict] = None) -> BaseStorageHandler:
        """
        Get a storage handler instance for the specified provider.
        
        Args:
            provider: Cloud provider name (aws, gcp, azure, etc.). 
                     If None, reads from STORAGE_CLOUD_PROVIDER environment variable.
            config: Optional configuration dictionary to pass to the handler.
                   If None, handler will use default configuration from environment.
        
        Returns:
            Instance of the appropriate storage handler
            
        Raises:
            ValueError: If provider is not supported or not configured
        """
        # Get provider from parameter or environment
        if provider is None:
            provider = os.getenv('STORAGE_CLOUD_PROVIDER', '').upper()
        else:
            provider = provider.upper()
        
        if not provider:
            raise ValueError(
                "Cloud provider not specified. Set STORAGE_CLOUD_PROVIDER environment variable "
                "or pass provider parameter. Supported providers: " + ", ".join(cls._handlers.keys())
            )
        
        # Get handler class from registry
        handler_class = cls._handlers.get(provider)
        
        if handler_class is None:
            raise ValueError(
                f"Unsupported cloud provider: '{provider}'. "
                f"Supported providers: {', '.join(cls._handlers.keys())}"
            )
        
        # Initialize and return handler
        config = config or {}
        
        logger.info(f"Initializing storage handler for provider: {provider}")
        
        try:
            return handler_class(config)
        except Exception as e:
            logger.error(f"Failed to initialize storage handler for {provider}: {str(e)}")
            raise
    
    @classmethod
    def register_handler(cls, provider: str, handler_class: type):
        """
        Register a new storage handler for a provider.
        Useful for adding custom storage handlers at runtime.
        
        Args:
            provider: Provider name (e.g., 'custom', 'local')
            handler_class: Handler class that extends BaseStorageHandler
        """
        if not issubclass(handler_class, BaseStorageHandler):
            raise ValueError(f"Handler class must extend BaseStorageHandler")
        
        cls._handlers[provider.upper()] = handler_class
        logger.info(f"Registered storage handler for provider: {provider}")
    
    @classmethod
    def get_supported_providers(cls) -> list:
        """
        Get list of supported cloud providers.
        
        Returns:
            List of provider names
        """
        return list(cls._handlers.keys())
