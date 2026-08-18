"""NotificationPort — cotacao via WhatsApp.

Dois caminhos, o port escolhe conforme configuracao:
  - `wa.me` deep link: imediato, sem aprovacao (default).
  - Meta Cloud API (template): mensagem proativa fora da janela de 24h exige
    template pre-aprovado; ver TODO(meta).
"""
from __future__ import annotations

import urllib.parse

from app.domain.models import Fornecedor


class WhatsAppWaMe:
    nome = "whatsapp-wame"

    async def cotar(self, fornecedor: Fornecedor, produto: str) -> dict:
        numero = ""
        if fornecedor.contato and fornecedor.contato.whatsapp:
            numero = fornecedor.contato.whatsapp[0]
        texto = f"Ola! Gostaria de cotar: {produto}. Voces tem disponivel? Qual o preco?"
        link = f"https://wa.me/{numero}?text={urllib.parse.quote(texto)}"
        return {"canal": "wa.me", "link": link, "numero": numero}


class WhatsAppCloudAPI:
    nome = "whatsapp-cloud"

    def __init__(self, access_token: str | None, phone_number_id: str | None) -> None:
        self.access_token = access_token
        self.phone_number_id = phone_number_id

    async def cotar(self, fornecedor: Fornecedor, produto: str) -> dict:
        if not (self.access_token and self.phone_number_id):
            raise RuntimeError(
                "WHATSAPP_ACCESS_TOKEN e WHATSAPP_PHONE_NUMBER_ID ausentes."
            )
        # TODO(meta): POST graph.facebook.com/v19.0/{phone_number_id}/messages
        #   type=template, template.name=<aprovado>, language=pt_BR, params=[produto]
        raise NotImplementedError("Envio via Meta Cloud API pendente (template).")
