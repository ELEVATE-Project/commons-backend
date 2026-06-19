from django.urls import re_path
from .consumers.Reflection_bedrock_consumer import ReflectionBedrockConsumer
from .consumers.async_chaupal_consumer import AsyncShikshalokamChaupalConsumer
from .consumers.async_consumer import AsyncSocketConsumer
from .consumers.free_flow_consumer import FreeFlowConsumer
from .consumers.guided_guest_consumer import GuidedGuestConsumer
from .consumers.mitra_bedrock_consumer import MitraBedrockConsumer
from .consumers.one_shot_bedrock_consumer import OneShotBedrockConsumer
from .consumers.oneshot_guest_consumer import OneShotGuestConsumer
from .consumers.shikshalokam_bedrock_consumer import ShikshalokamBedrockConsumer


websocket_urlpatterns = [
    re_path(r"ws/shikshalokam_new/$", ShikshalokamBedrockConsumer.as_asgi()),
    re_path(r"ws/guided_guest/$", GuidedGuestConsumer.as_asgi()),
    re_path(r"ws/reflection/$", ReflectionBedrockConsumer.as_asgi()),
    re_path(r"ws/shikshalokam_one_shot/$", OneShotBedrockConsumer.as_asgi()),
    re_path(r"ws/oneshot_guest/$", OneShotGuestConsumer.as_asgi()),
    re_path(r"ws/mitra/$", MitraBedrockConsumer.as_asgi()),
    re_path(r"ws/shikshalokam_chaupal/$", AsyncShikshalokamChaupalConsumer.as_asgi()),
    re_path(r"ws/common/$", AsyncSocketConsumer.as_asgi()),
    re_path(r"ws/free_flow/$", FreeFlowConsumer.as_asgi())
]
