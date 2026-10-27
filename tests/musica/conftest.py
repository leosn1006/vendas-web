"""Fixtures da Música: os casos de uso rodam com adaptadores falsos (sem banco, sem Celery, sem provedor)."""
import copy
import json
import os
import sys
from datetime import datetime
from pathlib import Path

import pytest

# Como no container (app/ copiado para /app): imports "musica", "database"...
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', 'app'))

from musica.adaptadores.arquivos import Arquivos  # noqa: E402
from musica.adaptadores.gerador_simulado import GeradorSimulado  # noqa: E402
from musica.adaptadores.letra_openai import LetraSimulada  # noqa: E402
from musica.fabrica import Servicos  # noqa: E402

PASTA_CONTEUDO = Path(__file__).resolve().parents[2] / 'app' / 'musica' / 'conteudo'


class RepositorioMemoria:
    """O mesmo contrato de portas.Repositorio, em memória."""

    def __init__(self):
        self.musicas, self.vinculos, self.pedidos, self.itens = {}, {}, {}, {}
        self.geracoes_24h = 0

    def criar(self, produto_id, respostas, email, whatsapp, ip, pedido_origem_id, dominio):
        mid = len(self.musicas) + 1
        self.musicas[mid] = {
            'id': mid, 'token': f'{mid:032x}', 'produto_id': produto_id, 'pedido_id': None,
            'pedido_origem_id': pedido_origem_id, 'dominio': dominio, 'status': 'escrevendo',
            'respostas': respostas, 'email': email, 'whatsapp': whatsapp, 'ip': ip, 'titulo': None,
            'letra_exibicao': None, 'letra_suno': None, 'modelo_letra': None, 'ajustes_letra': 0, 'provedor': None,
            'job_id': None, 'gerando_desde': None, 'geracoes': 0, 'outras_versoes': 0, 'faixas': None, 'erro': None,
            'liberada_em': None, 'video_status': None, 'video_versao': None, 'video_legenda': None, 'video_erro': None,
            'presente_nome': None, 'presente_email': None, 'presente_mensagem': None, 'presente_em': None,
            'presente_enviado_em': None, 'presente_tentativas': 0, 'presente_thread_id': None,
            'presente_falhou_em': None, 'checkout_aberto_em': None,
            'lembrete_etapa': None, 'lembrete_desde': None, 'lembretes_enviados': 0, 'lembrete_ultimo_em': None,
            'sem_lembretes': 0, 'em_checkout': 0, 'pedido_aberto_id': None, 'pedido_aberto_plano': None,
            'presente_whatsapp': None, 'presente_wa_msg_id': None, 'presente_wa_status': None,
            'presente_wa_entregue_em': None, 'presente_wa_link_em': None, 'comprador_wa_msg_id': None,
            'comprador_wa_em': None,
        }
        return dict(self.musicas[mid])

    def por_id(self, musica_id):
        m = self.musicas.get(musica_id)
        return copy.deepcopy(m) if m else None

    def por_token(self, token):
        return next((self.por_id(m['id']) for m in self.musicas.values() if m['token'] == token), None)

    def por_job(self, job_id):
        return next((self.por_id(m['id']) for m in self.musicas.values() if m['job_id'] == job_id), None)

    def do_pedido(self, pedido_id):
        mid = self.vinculos.get(pedido_id)
        return self.por_id(mid) if mid else None

    def atualizar(self, musica_id, **campos):
        self.musicas[musica_id].update(campos)

    def trocar_status(self, musica_id, de, para):
        if self.musicas[musica_id]['status'] != de:
            return False
        self.musicas[musica_id]['status'] = para
        return True

    def geracoes_recentes(self, email, ip, horas=24):
        return self.geracoes_24h

    def musicas_criadas_recentes(self, email, ip, horas=24):
        return sum(1 for m in self.musicas.values() if m['email'] == email or m['ip'] == ip)

    def videos_parados(self, minutos):
        return [{'id': m['id'], 'video_erro': m['video_erro']} for m in self.musicas.values()
                if m['video_status'] == 'fazendo' and m.get('_parado')]

    def vincular_pedido(self, musica_id, pedido_id):
        self.vinculos[pedido_id] = musica_id

    def pedido_pago(self, pedido_id):
        p = self.pedidos.get(pedido_id)
        return p if p and p['estado_id'] == 1000 else None

    def pedido_por_guid(self, guid):
        return next((p for p in self.pedidos.values() if p['guid'] == guid), None)

    def recursos_do_pedido(self, pedido_id):
        return set(self.itens.get(pedido_id, ()))

    def marcar_liberada(self, musica_id, pedido_id):
        m = self.musicas[musica_id]
        if m['liberada_em']:
            return False
        m['liberada_em'], m['pedido_id'] = datetime.now(), pedido_id
        return True

    def pagas_sem_liberar(self):
        return [pid for pid, mid in self.vinculos.items()
                if self.pedido_pago(pid) and not self.musicas[mid]['liberada_em']]

    def presentes_para_enviar(self):
        agora = datetime.now()
        def falta(m):
            return ((m['presente_email'] and not m['presente_thread_id'] and not m['presente_falhou_em'])
                    or (m['presente_whatsapp'] and not m['presente_wa_msg_id']
                        and (m['presente_wa_status'] or '') in ('', 'erro1', 'erro2')))
        return [self.por_id(m['id']) for m in self.musicas.values()
                if m['liberada_em'] and not m['presente_enviado_em'] and falta(m)
                and (m['presente_em'] is None or m['presente_em'] <= agora)]

    def por_wamid_presente(self, wamid):
        return next((self.por_id(m['id']) for m in self.musicas.values() if wamid and m['presente_wa_msg_id'] == wamid), None)

    def presente_wa_sem_wamid(self, telefone):
        return any(m['presente_whatsapp'] and not m['presente_wa_msg_id'] and m['presente_enviado_em']
                   and len(telefone) >= 8 and m['presente_whatsapp'][-8:] == telefone[-8:] for m in self.musicas.values())

    def marcar_presente_wa(self, musica_id, status):
        m = self.musicas[musica_id]
        if status == 'entregue':
            if m['presente_wa_status'] != 'enviado':
                return False
            m['presente_wa_status'], m['presente_wa_entregue_em'] = 'entregue', datetime.now()
            return True
        if m['presente_wa_status'] not in (None, 'enviado', 'erro1', 'erro2'):
            return False
        m['presente_wa_status'] = 'falhou'
        return True

    def numero_avisos(self, produto_id):
        return '1376511528883172'

    def marcar_presente_enviado(self, musica_id):
        if self.musicas[musica_id]['presente_enviado_em']:
            return False
        self.musicas[musica_id]['presente_enviado_em'] = datetime.now()
        return True

    def presente_por_devolucao(self, thread_id, recusados):
        for m in self.musicas.values():
            if not m['presente_falhou_em'] and ((thread_id and m['presente_thread_id'] == thread_id) or
                                                (m['presente_email'] and m['presente_email'] in (recusados or ()))):
                return self.por_id(m['id'])
        return None

    def presentes_sem_confirmacao(self, minutos):
        return [self.por_id(m['id']) for m in self.musicas.values() if m.get('_envio_interrompido')]

    def candidatas_lembrete(self):
        """Como o SQL: não pagas, com e-mail, sem "não quero mais", na letra ou na prévia; `em_checkout` = o checkout
        desta música abriu (`checkout_aberto_em`) ou o teste marcou um pedido esperando pagamento (`em_checkout`)."""
        saida = []
        for m in self.musicas.values():
            if m['liberada_em'] or not m['email'] or m['sem_lembretes'] or m['status'] not in ('letra_pronta', 'previa_pronta'):
                continue
            copia = self.por_id(m['id'])
            copia['em_checkout'] = int(bool(m['em_checkout'] or m['checkout_aberto_em']))
            saida.append(copia)
        return saida

    def paradas(self, status, minutos):
        return []

    def nao_pagas_antigas(self, dias):
        return []

    def apagar(self, musica_id):
        self.musicas.pop(musica_id, None)

    def remetente_do_produto(self, produto_id):
        return {}


class AgendaMemoria:
    def __init__(self):
        self.chamadas = []

    def escrever_letra(self, musica_id, ajuste=None):
        self.chamadas.append(('letra', musica_id, ajuste))

    def consultar(self, musica_id, depois_de_segundos=0):
        self.chamadas.append(('consultar', musica_id, depois_de_segundos))

    def fazer_video(self, musica_id):
        self.chamadas.append(('video', musica_id))

    def enviar_presentes(self):
        self.chamadas.append(('presentes',))

    def whatsapp_comprador(self, musica_id):
        self.chamadas.append(('whatsapp_comprador', musica_id))

    def reler_status_whatsapp(self, statuses, depois_de_segundos):
        self.chamadas.append(('reler_status_whatsapp', statuses, depois_de_segundos))


class NotificadorMemoria:
    def __init__(self):
        self.emails, self.whatsapps, self.alertas = [], [], []

    def email(self, produto_id, destino, assunto, html, cc=None):
        self.emails.append({'produto_id': produto_id, 'destino': destino, 'assunto': assunto, 'html': html, 'cc': cc})
        return f'thread-{len(self.emails)}'

    def whatsapp(self, telefone, modelo, variaveis, payload_botao=None, produto_id=None):
        self.whatsapps.append((telefone, modelo, variaveis, payload_botao))
        return f'wamid-{len(self.whatsapps)}'

    def whatsapp_texto(self, telefone, texto, produto_id=None):
        self.whatsapps.append((telefone, 'texto', [texto], None))
        return f'wamid-{len(self.whatsapps)}'

    def equipe(self, mensagem):
        self.alertas.append(mensagem)


class AudioFalso:
    """Grava arquivos de mentira no lugar do download e do corte."""
    def __init__(self):
        self.falhar = False

    def baixar(self, url, destino):
        if self.falhar:
            raise OSError('download falhou')
        destino.parent.mkdir(parents=True, exist_ok=True)
        destino.write_bytes(b'mp3')

    def cortar_previa(self, origem, destino, inicio, segundos):
        destino.parent.mkdir(parents=True, exist_ok=True)
        destino.write_bytes(f'{inicio}:{segundos}'.encode())


class VideoFalso:
    max_fotos = 20

    def __init__(self):
        self.montados = []

    def preparar_foto(self, origem, destino):
        destino.write_bytes(origem.read())

    def montar(self, fotos, musica, saida, titulo, para, de, legenda_ass=None):
        self.montados.append((len(fotos), titulo, para, de))
        saida.parent.mkdir(parents=True, exist_ok=True)
        saida.write_bytes(b'mp4')


@pytest.fixture
def s(tmp_path):
    return Servicos(
        gerador=GeradorSimulado(segundos_ate_pronta=0),
        escritor=LetraSimulada(),
        transcritor=None,
        audio=AudioFalso(),
        video=VideoFalso(),
        repositorio=RepositorioMemoria(),
        notificador=NotificadorMemoria(),
        agenda=AgendaMemoria(),
        arquivos=Arquivos(tmp_path),
        instrucoes_letra='instruções',
        estilos=json.loads((PASTA_CONTEUDO / 'estilos.json').read_text(encoding='utf-8')),
    )


RESPOSTAS = {'para_quem': 'Mãe', 'nome': 'Helena', 'apelido': 'Dona Lena', 'lembrancas': 'Bolo de fubá aos domingos',
             'de': 'Patrícia', 'estilo': 'sertanejo', 'clima': 'emocionante', 'voz': 'feminina'}
