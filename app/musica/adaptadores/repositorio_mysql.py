"""Repositorio no MySQL do sistema (database.db). Todo o SQL do módulo Música fica aqui."""
import json
import secrets

from database import db
from musica.dominio.regras import respostas_atuais

_CAMPOS_JSON = ('respostas', 'faixas')
_ESTADO_PAGO = 1000   # pedido web pago


def _musica(linha):
    if not linha:
        return None
    m = dict(linha)
    for campo in _CAMPOS_JSON:
        if isinstance(m.get(campo), (str, bytes)):
            m[campo] = json.loads(m[campo])
    respostas_atuais(m.get('respostas'))   # estilo que saiu do quiz → o de hoje (letra e música iguais)
    return m


class RepositorioMysql:
    def criar(self, produto_id, respostas, email, whatsapp, ip, pedido_origem_id, dominio):
        token = secrets.token_hex(16)
        musica_id = db.execute_query(
            """INSERT INTO musicas (token, produto_id, pedido_origem_id, dominio, status, respostas, email, whatsapp, ip)
               VALUES (%s, %s, %s, %s, 'escrevendo', %s, %s, %s, %s)""",
            (token, produto_id, pedido_origem_id, dominio or None, json.dumps(respostas, ensure_ascii=False),
             email or None, whatsapp or None, ip or None))
        return self.por_id(musica_id)

    def por_id(self, musica_id):
        return _musica(db.execute_query("SELECT * FROM musicas WHERE id = %s", (musica_id,), fetch_one=True))

    def por_token(self, token):
        return _musica(db.execute_query("SELECT * FROM musicas WHERE token = %s", (token,), fetch_one=True))

    def por_job(self, job_id):
        return _musica(db.execute_query("SELECT * FROM musicas WHERE job_id = %s", (job_id,), fetch_one=True))

    def do_pedido(self, pedido_id):
        """A música que este pedido do checkout compra (musica_pedidos)."""
        return _musica(db.execute_query("SELECT m.* FROM musica_pedidos mp JOIN musicas m ON m.id = mp.musica_id "
                                        "WHERE mp.pedido_id = %s", (pedido_id,), fetch_one=True))

    def atualizar(self, musica_id, **campos):
        if not campos:
            return
        for campo in set(_CAMPOS_JSON) & campos.keys():
            if campos[campo] is not None:
                campos[campo] = json.dumps(campos[campo], ensure_ascii=False)
        colunas = ', '.join(f'{nome} = %s' for nome in campos)   # nomes vêm do código, nunca do usuário
        db.execute_query(f"UPDATE musicas SET {colunas} WHERE id = %s", (*campos.values(), musica_id))

    def trocar_status(self, musica_id, de, para):
        """Troca só se ainda estiver no status esperado (evita processar ou gastar crédito em dobro)."""
        return db.execute_query("UPDATE musicas SET status = %s WHERE id = %s AND status = %s",
                                (para, musica_id, de), return_rowcount=True) == 1

    def geracoes_recentes(self, email, ip, horas=24):
        """Gerações que a CLIENTE pediu ('criar a música' + 'outra versão'). As novas tentativas automáticas
        depois de uma falha do gerador são nossas e não contam no limite dela."""
        linha = db.execute_query(
            """SELECT COALESCE(SUM(CASE WHEN geracoes > 0 THEN 1 + outras_versoes ELSE 0 END), 0) AS total FROM musicas
               WHERE criado_em >= NOW() - INTERVAL %s HOUR AND (email = %s OR ip = %s)""",
            (horas, email or '', ip or ''), fetch_one=True)
        return int(linha['total']) if linha else 0

    def musicas_criadas_recentes(self, email, ip, horas=24):
        linha = db.execute_query("SELECT COUNT(*) AS total FROM musicas WHERE criado_em >= NOW() - INTERVAL %s HOUR "
                                 "AND (email = %s OR ip = %s)", (horas, email or '', ip or ''), fetch_one=True)
        return int(linha['total']) if linha else 0

    def videos_parados(self, minutos):
        """Videoclipes em 'fazendo' sem mudança há mais de `minutos` (a montagem leva de 1 a 4 min)."""
        linhas = db.execute_query("SELECT id, video_erro FROM musicas WHERE video_status = 'fazendo' "
                                  "AND atualizado_em < NOW() - INTERVAL %s MINUTE LIMIT 50", (minutos,), fetch_all=True) or []
        return [dict(l) for l in linhas]

    def vincular_pedido(self, musica_id, pedido_id):
        """Uma música por pedido (o mesmo rascunho reaproveitado para outra música troca o vínculo); uma música
        pode estar em vários pedidos (mais de um PIX gerado) — o primeiro pago libera."""
        db.execute_query("INSERT INTO musica_pedidos (pedido_id, musica_id) VALUES (%s, %s) "
                         "ON DUPLICATE KEY UPDATE musica_id = VALUES(musica_id)", (pedido_id, musica_id))
        # Atribuição do Google Ads: a campanha (GCLID) ficou no rascunho da landing em que a música nasceu.
        # Se a compra criou um pedido novo (ex.: voltou pelo e-mail de lembrete), ele herda a campanha.
        db.execute_query(
            """UPDATE pedidos p JOIN musicas m ON m.id = %s JOIN pedidos o ON o.id = m.pedido_origem_id
               SET p.gclid = o.gclid, p.campaignid = o.campaignid, p.adgroupid = o.adgroupid,
                   p.creative = o.creative, p.matchtype = o.matchtype, p.device = o.device,
                   p.placement = o.placement, p.video_id = o.video_id
               WHERE p.id = %s AND o.id <> p.id AND COALESCE(p.gclid, '') = '' AND COALESCE(o.gclid, '') <> ''""",
            (musica_id, pedido_id))

    def pedido_pago(self, pedido_id):
        return db.execute_query("SELECT id, guid, email, contact_name, produto_id, dns_origem FROM pedidos "
                                "WHERE id = %s AND estado_id = %s", (pedido_id, _ESTADO_PAGO), fetch_one=True)

    def pedido_por_guid(self, guid):
        return db.execute_query("SELECT id, guid, email, contact_name, produto_id, estado_id FROM pedidos "
                                "WHERE guid = %s", (guid,), fetch_one=True)

    def recursos_do_pedido(self, pedido_id):
        linhas = db.execute_query("SELECT DISTINCT recurso FROM pedido_itens WHERE pedido_id = %s AND recurso IS NOT NULL",
                                  (pedido_id,), fetch_all=True) or []
        return {l['recurso'] for l in linhas}

    def marcar_liberada(self, musica_id, pedido_id):
        return db.execute_query("UPDATE musicas SET liberada_em = NOW(), pedido_id = %s WHERE id = %s AND liberada_em IS NULL",
                                (pedido_id, musica_id), return_rowcount=True) == 1

    def pagas_sem_liberar(self):
        linhas = db.execute_query(
            """SELECT mp.pedido_id FROM musica_pedidos mp
               JOIN musicas m ON m.id = mp.musica_id JOIN pedidos p ON p.id = mp.pedido_id
               WHERE m.liberada_em IS NULL AND p.estado_id = %s
                 AND p.data_pagamento >= NOW() - INTERVAL 30 DAY""", (_ESTADO_PAGO,), fetch_all=True) or []
        return [l['pedido_id'] for l in linhas]

    def presentes_para_enviar(self):
        """Presentes cujo horário chegou e que ainda têm um canal por sair: o e-mail (sem thread = não saiu ou é nova
        tentativa) e/ou o WhatsApp (sem wamid; sem status ou com erro passageiro 'erroN')."""
        linhas = db.execute_query(
            """SELECT * FROM musicas WHERE liberada_em IS NOT NULL AND presente_enviado_em IS NULL
               AND (presente_em IS NULL OR presente_em <= NOW())
               AND ((presente_email IS NOT NULL AND presente_thread_id IS NULL AND presente_falhou_em IS NULL)
                    OR (presente_whatsapp IS NOT NULL AND presente_wa_msg_id IS NULL
                        AND (presente_wa_status IS NULL OR presente_wa_status LIKE 'erro%%')))""",
            fetch_all=True) or []
        return [_musica(l) for l in linhas]

    def marcar_presente_enviado(self, musica_id):
        return db.execute_query("UPDATE musicas SET presente_enviado_em = NOW() WHERE id = %s AND presente_enviado_em IS NULL",
                                (musica_id,), return_rowcount=True) == 1

    def presentes_sem_confirmacao(self, minutos):
        """Marcados como enviados há mais de `minutos` com um canal sem confirmação (e-mail sem thread do Gmail,
        WhatsApp sem wamid nem status): o envio foi interrompido."""
        linhas = db.execute_query(
            """SELECT * FROM musicas WHERE presente_enviado_em < NOW() - INTERVAL %s MINUTE
               AND presente_enviado_em >= NOW() - INTERVAL 3 DAY
               AND ((presente_email IS NOT NULL AND presente_thread_id IS NULL AND presente_falhou_em IS NULL)
                    OR (presente_whatsapp IS NOT NULL AND presente_wa_msg_id IS NULL AND presente_wa_status IS NULL))
               LIMIT 50""", (minutos,), fetch_all=True) or []
        return [_musica(l) for l in linhas]

    def por_wamid_presente(self, wamid):
        """A música cujo presente_surpresa tem este id de mensagem da Meta (os status de entrega chegam por ele)."""
        if not wamid:
            return None
        return _musica(db.execute_query("SELECT * FROM musicas WHERE presente_wa_msg_id = %s", (wamid,), fetch_one=True))

    def marcar_presente_wa(self, musica_id, status):
        """Entregue (só a partir de 'enviado') ou falhou (se ainda não chegou nem falhou). True se mudou agora —
        é o que garante um aviso só, mesmo com a Meta mandando 'entregue' e 'lido'."""
        if status == 'entregue':
            return db.execute_query("UPDATE musicas SET presente_wa_status = 'entregue', presente_wa_entregue_em = NOW() "
                                    "WHERE id = %s AND presente_wa_status = 'enviado'", (musica_id,), return_rowcount=True) == 1
        return db.execute_query("UPDATE musicas SET presente_wa_status = 'falhou' WHERE id = %s "
                                "AND (presente_wa_status IS NULL OR presente_wa_status = 'enviado' "
                                "OR presente_wa_status LIKE 'erro%%')",
                                (musica_id,), return_rowcount=True) == 1

    def presente_wa_sem_wamid(self, telefone):
        """Presente_surpresa saindo agora para este número (marcado há até 10 min, wamid ainda não gravado).
        Compara os 8 últimos dígitos: a Meta às vezes devolve o celular sem o 9."""
        if len(telefone or '') < 8:
            return False
        return bool(db.execute_query(
            """SELECT 1 FROM musicas WHERE presente_whatsapp IS NOT NULL AND presente_wa_msg_id IS NULL
               AND presente_enviado_em >= NOW() - INTERVAL 10 MINUTE AND RIGHT(presente_whatsapp, 8) = RIGHT(%s, 8)
               LIMIT 1""", (telefone,), fetch_one=True))

    def numero_avisos(self, produto_id):
        """O api_phone_number_id do número só de avisos do produto (telefones_produto.responde_mensagens = 0)."""
        linha = db.execute_query("SELECT api_phone_number_id FROM telefones_produto WHERE produto_id = %s "
                                 "AND responde_mensagens = 0 AND api_phone_number_id IS NOT NULL ORDER BY id LIMIT 1",
                                 (produto_id,), fetch_one=True)
        return linha['api_phone_number_id'] if linha else None

    def presente_por_devolucao(self, thread_id, recusados):
        """A música cujo presente voltou: pelo thread do Gmail do envio ou, sem ele, pelo endereço exato de quem
        recebe entre os recusados (envios dos últimos 3 dias ainda não dados como perdidos)."""
        if thread_id:
            linha = db.execute_query("SELECT * FROM musicas WHERE presente_thread_id = %s AND presente_falhou_em IS NULL",
                                     (thread_id,), fetch_one=True)
            if linha:
                return _musica(linha)
        if not recusados:
            return None
        marcas = ', '.join(['%s'] * len(recusados))
        return _musica(db.execute_query(
            f"""SELECT * FROM musicas WHERE LOWER(presente_email) IN ({marcas}) AND presente_falhou_em IS NULL
               AND presente_enviado_em >= NOW() - INTERVAL 3 DAY ORDER BY presente_enviado_em DESC LIMIT 1""",
            tuple(recusados), fetch_one=True))

    def candidatas_lembrete(self):
        """Músicas que podem receber lembrete (a pessoa, a série e a hora saem de regras.escolher_lembretes /
        proximo_lembrete): não pagas, com e-mail, dos últimos 5 dias, paradas na letra ou na prévia (o checkout é a
        prévia que foi ao pagamento), de e-mails sem "não quero mais" nos últimos 90 dias e sem compra depois desta
        música nem nas últimas 24 h. "Mesmo e-mail" = o e-mail como gravado: criar_musica o grava já em
        regras.chave_email (sem espaços, minúsculas) — e assim usa o índice idx_musicas_email.
        `em_checkout`: o checkout DESTA música abriu ou há pedido dela esperando pagamento (1002);
        `pedido_aberto_id`/`_plano`: o pedido com o PIX ainda válido e o plano (fora o padrão), para o link reabri-lo."""
        linhas = db.execute_query(
            """SELECT m.id, m.token, m.produto_id, m.dominio, m.status, m.respostas, m.email, m.criado_em,
                      m.liberada_em, m.lembrete_etapa,
                      (m.checkout_aberto_em IS NOT NULL OR EXISTS (
                           SELECT 1 FROM musica_pedidos mp JOIN pedidos p ON p.id = mp.pedido_id
                           WHERE mp.musica_id = m.id AND p.estado_id = 1002)) AS em_checkout,
                      a.id AS pedido_aberto_id, IF(pp.padrao = 1, NULL, pp.slug) AS pedido_aberto_plano
               FROM musicas m
               LEFT JOIN musica_lembretes_saida saida
                      ON saida.email_chave = m.email AND saida.em >= NOW() - INTERVAL 90 DAY
               LEFT JOIN pedidos a ON a.id = (
                   SELECT MAX(p.id) FROM musica_pedidos mp JOIN pedidos p ON p.id = mp.pedido_id
                   WHERE mp.musica_id = m.id AND p.estado_id = 1002
                     AND (p.expiracao_solicitacao_bb IS NULL OR p.expiracao_solicitacao_bb > NOW()))
               LEFT JOIN produto_planos pp ON pp.id = a.plano_id
               WHERE m.liberada_em IS NULL AND m.email IS NOT NULL
                 AND m.criado_em >= NOW() - INTERVAL 5 DAY
                 AND m.status IN ('letra_pronta', 'previa_pronta')
                 AND saida.email_chave IS NULL
                 AND NOT EXISTS (SELECT 1 FROM musicas outra WHERE outra.email = m.email
                                 AND outra.liberada_em >= LEAST(m.criado_em, NOW() - INTERVAL 1 DAY))
               ORDER BY m.id DESC
               LIMIT 5000""", fetch_all=True) or []   # trava de segurança; o normal é bem menos (5 dias de músicas)
        return [_musica(l) for l in linhas]

    def series_lembrete(self):
        """As séries da janela que importa (5 dias de músicas + 3 de validade), com o status da música da vez."""
        linhas = db.execute_query(
            """SELECT l.email_chave, l.etapa, l.inicio, l.desde, l.enviados, l.ultimo_em, l.musica_id,
                      m.status AS musica_status
               FROM musica_lembretes l LEFT JOIN musicas m ON m.id = l.musica_id
               WHERE l.inicio >= NOW() - INTERVAL 8 DAY""", fetch_all=True) or []
        return {(l['email_chave'], l['etapa']): {'inicio': l['inicio'], 'desde': l['desde'], 'enviados': l['enviados'],
                                                 'ultimo_em': l['ultimo_em'], 'musica_id': l['musica_id'],
                                                 'musica_status': l['musica_status']}
                for l in linhas}

    def salvar_serie(self, chave_email, etapa, inicio, desde, enviados, ultimo_em, musica_id):
        db.execute_query(
            """INSERT INTO musica_lembretes (email_chave, etapa, inicio, desde, enviados, ultimo_em, musica_id)
               VALUES (%s, %s, %s, %s, %s, %s, %s)
               ON DUPLICATE KEY UPDATE inicio = VALUES(inicio), desde = VALUES(desde), enviados = VALUES(enviados),
                                       ultimo_em = VALUES(ultimo_em), musica_id = VALUES(musica_id)""",
            (chave_email, etapa, inicio, desde, enviados, ultimo_em, musica_id))

    def parar_lembretes_email(self, chave_email):
        db.execute_query("INSERT INTO musica_lembretes_saida (email_chave, em) VALUES (%s, NOW()) "
                         "ON DUPLICATE KEY UPDATE em = NOW()", (chave_email,))

    def paradas(self, status, minutos):
        """Músicas presas num status de espera há mais de `minutos` (worker reiniciado, tarefa perdida)."""
        coluna = 'gerando_desde' if status == 'gerando' else 'atualizado_em'
        linhas = db.execute_query(f"SELECT id FROM musicas WHERE status = %s AND {coluna} < NOW() - INTERVAL %s MINUTE "
                                  "AND criado_em >= NOW() - INTERVAL 2 DAY LIMIT 200", (status, minutos), fetch_all=True) or []
        return [l['id'] for l in linhas]

    def nao_pagas_antigas(self, dias):
        linhas = db.execute_query(
            """SELECT m.id, m.token FROM musicas m
               WHERE m.liberada_em IS NULL AND m.criado_em < NOW() - INTERVAL %s DAY
                 AND NOT EXISTS (SELECT 1 FROM musica_pedidos mp JOIN pedidos p ON p.id = mp.pedido_id
                                 WHERE mp.musica_id = m.id AND p.estado_id = %s)
               LIMIT 500""", (dias, _ESTADO_PAGO), fetch_all=True) or []
        return [dict(l) for l in linhas]

    def apagar(self, musica_id):
        db.execute_query("DELETE FROM musicas WHERE id = %s AND liberada_em IS NULL", (musica_id,))

    def produto_musica(self):
        """O produto que vende a Música: ativo, à venda no site e com plano padrão cujo principal é de música.
        Configuração no banco (CLAUDE.md: nada hardcoded por produto). Mais de um: o de menor id."""
        return db.execute_query(
            """SELECT p.* FROM produtos p
               WHERE p.ativo = 1 AND p.disponivel_web = 1 AND EXISTS (
                   SELECT 1 FROM produto_planos pp
                   JOIN plano_entregaveis pe ON pe.plano_id = pp.id AND pe.papel = 'principal'
                   JOIN entregaveis e ON e.id = pe.entregavel_id AND e.tipo = 'musica'
                   WHERE pp.produto_id = p.id AND pp.padrao = 1 AND pp.ativo = 1)
               ORDER BY p.id LIMIT 1""", fetch_one=True)

    def empresa_do_produto(self, produto):
        """A empresa que vende (termos e privacidade): a configuração fiscal ligada ao produto (nfe_config_id;
        a Música é da LBE). Ligar o produto à empresa não emite NF-e: ele está com nfe_automatica = 0."""
        from database import get_empresa_produto
        return get_empresa_produto(produto)

    def remetente_do_produto(self, produto_id):
        return db.execute_query("SELECT id, nome, email_remetente, email_nome_remetente, email_cor_primaria, email_cor_secundaria "
                                "FROM produtos WHERE id = %s",
                                (produto_id,), fetch_one=True) or {}
