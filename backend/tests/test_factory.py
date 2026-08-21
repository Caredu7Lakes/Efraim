from app.config import get_settings
from app.sourcing.factory import montar_orquestrador


def test_cache_e_compartilhado_entre_execucoes():
    """Achado em teste real (19/08): `montar_orquestrador` e' chamado de novo
    a cada job (jobs/tasks.py), e antes disso criava um CacheTTL vazio toda
    vez - o cache nunca sobrevivia entre duas buscas HTTP separadas."""
    cfg = get_settings()
    orq1 = montar_orquestrador(cfg)
    orq2 = montar_orquestrador(cfg)
    assert orq1.cache is orq2.cache
