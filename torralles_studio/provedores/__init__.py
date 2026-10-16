from .busca import BraveBusca, TavilyBusca
from .juiz_video import GeminiVideoJuiz
from .midia import FreesoundMidia, OpenverseMidia, PexelsMidia, PixabayMidia
from .imagem import FalImagem, GeminiImagem, OpenAIImagem, PollinationsImagem
from .texto import AnthropicTexto, GeminiTexto, OpenAICompatTexto
from .video import FalVideo, KenBurnsVideo
from .voz import EdgeVoz, ElevenLabsVoz, OpenAIVoz

# Nome usado no campo `classe` do config/fallbacks.toml.
CLASSES = {
    "openai_compat": OpenAICompatTexto,
    "anthropic": AnthropicTexto,
    "gemini_texto": GeminiTexto,
    "tavily": TavilyBusca,
    "brave": BraveBusca,
    "gemini_imagem": GeminiImagem,
    "openai_imagem": OpenAIImagem,
    "fal_imagem": FalImagem,
    "pollinations": PollinationsImagem,
    "elevenlabs": ElevenLabsVoz,
    "openai_voz": OpenAIVoz,
    "edge_tts": EdgeVoz,
    "fal_video": FalVideo,
    "ken_burns": KenBurnsVideo,
    "gemini_video": GeminiVideoJuiz,
    "pexels": PexelsMidia,
    "pixabay": PixabayMidia,
    "openverse": OpenverseMidia,
    "freesound": FreesoundMidia,
}
