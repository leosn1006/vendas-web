/*
 * Credencial do cartão no checkout (checkout.html e checkout-2.html).
 *
 * O número do cartão e o CVV NUNCA vão para o nosso backend (PCI SAQ A-EP): o script Silent
 * Order Post (SOP) da Cielo lê os campos desta página e manda o cartão direto para a Cielo,
 * que devolve um PaymentToken (GUID, uso único, ~20 min). O backend autoriza só com o token.
 *
 * Fluxo de obterCredencial():
 *   1. POST /api/v1/cartao/sop-token  → AccessToken do SOP (um novo a cada tentativa)
 *   2. carrega o script do SOP (uma vez só)
 *   3. copia os campos visíveis para inputs ocultos no formato que o script exige
 *   4. bpSop_silentOrderPost → PaymentToken
 *   5. limpa os inputs ocultos
 *
 * Devolve { tipo: 'sop', payment_token, bin, bandeira }. As wallets (Google Pay / Apple Pay)
 * entram aqui depois como outros tipos de credencial — o resto do checkout não muda.
 */
(function (global) {
    'use strict';

    const SOP_SCRIPT = 'https://www.pagador.com.br/post/scripts/silentorderpost-1.0.min.js';
    const TEMPO_MAXIMO_MS = 30000;
    const MSG_INSTABILIDADE = 'Tivemos uma instabilidade ao confirmar seu pagamento. Tente novamente ou pague com Pix.';
    const MSG_DADOS = 'Não conseguimos validar os dados do cartão. Confira e tente de novo, ou pague com Pix.';
    const NOMES_CAMPOS = {
        'bp-sop-cardnumber': 'Número do cartão',
        'bp-sop-cardexpirationdate': 'Validade do cartão',
        'bp-sop-cardcvv': 'Código de segurança (CVV)',
        'bp-sop-cardholdername': 'Nome impresso no cartão',
    };

    class ErroCartao extends Error {
        constructor(mensagemCliente, detalhe) {
            super(mensagemCliente);
            this.mensagemCliente = mensagemCliente;
            this.detalhe = detalhe;
        }
    }

    let scriptSop = null;
    function carregarScriptSop() {
        if (typeof global.bpSop_silentOrderPost === 'function') return Promise.resolve();
        if (scriptSop) return scriptSop;
        scriptSop = new Promise((resolve, reject) => {
            const s = document.createElement('script');
            s.src = SOP_SCRIPT;
            s.async = true;
            s.onload = () => resolve();
            s.onerror = () => { scriptSop = null; reject(new ErroCartao(MSG_INSTABILIDADE, 'script SOP não carregou')); };
            document.head.appendChild(s);
        });
        return scriptSop;
    }

    // O script só aceita [a-zA-Z ] no nome do titular: "João da Conceição" → "JOAO DA CONCEICAO".
    function nomeParaSop(nome) {
        return (nome || '').normalize('NFD').replace(/[̀-ͯ]/g, '')
            .replace(/[^a-zA-Z ]/g, ' ').replace(/\s+/g, ' ').trim().toUpperCase().slice(0, 64);
    }

    function el(id) { return document.getElementById(id); }

    // Inputs ocultos (sem `name`) com as classes que o script do SOP procura. Os visíveis ficam
    // como estão (máscara com espaços, mês/ano separados, acentos), por isso a cópia.
    function preencherCamposSop() {
        el('sopNumero').value = el('inputNumeroCartao').value.replace(/\D/g, '');
        el('sopValidade').value = `${el('selectMes').value}/${el('selectAno').value}`;
        el('sopCvv').value = el('inputCvv').value.replace(/\D/g, '');
        el('sopTitular').value = nomeParaSop(el('inputTitular').value);
    }

    function limparCamposSop() {
        ['sopNumero', 'sopValidade', 'sopCvv', 'sopTitular'].forEach((id) => { if (el(id)) el(id).value = ''; });
    }

    function mensagemInvalidos(campos) {
        const nomes = [...new Set((campos || []).map((c) => NOMES_CAMPOS[c.Field]).filter(Boolean))];
        return nomes.length ? `Confira: ${nomes.join(', ')}.` : MSG_DADOS;
    }

    async function pedirAccessToken(produtoId) {
        let resp, dados = {};
        try {
            resp = await fetch('/api/v1/cartao/sop-token', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ produto_id: produtoId }),
            });
            dados = await resp.json().catch(() => ({}));
        } catch (e) {
            throw new ErroCartao(MSG_INSTABILIDADE, e);
        }
        if (!resp.ok || !dados.access_token) throw new ErroCartao(dados.mensagem || MSG_INSTABILIDADE, dados.erro);
        return dados;
    }

    function tokenizar(accessToken, ambiente) {
        return new Promise((resolve, reject) => {
            const limite = setTimeout(() => reject(new ErroCartao(MSG_INSTABILIDADE, 'tempo esgotado no SOP')), TEMPO_MAXIMO_MS);
            const fim = (fn) => (arg) => { clearTimeout(limite); fn(arg); };
            global.bpSop_silentOrderPost({
                accessToken: accessToken,
                environment: ambiente,
                language: 'PT',
                onSuccess: fim((r) => (r && r.PaymentToken)
                    ? resolve(r)
                    : reject(new ErroCartao(MSG_INSTABILIDADE, 'SOP sem PaymentToken'))),
                // 400 = a Cielo recusou os dados enviados; demais = instabilidade/token vencido.
                onError: fim((e) => reject(new ErroCartao(e && e.Code === 400 ? MSG_DADOS : MSG_INSTABILIDADE,
                                                          e && e.Code))),
                onInvalid: fim((campos) => reject(new ErroCartao(mensagemInvalidos(campos), 'campos inválidos'))),
            });
        });
    }

    async function obterCredencial({ produtoId, bandeira }) {
        const bin = el('inputNumeroCartao').value.replace(/\D/g, '').slice(0, 6);
        const { access_token, ambiente } = await pedirAccessToken(produtoId);
        await carregarScriptSop();
        preencherCamposSop();
        try {
            const r = await tokenizar(access_token, ambiente);
            return { tipo: 'sop', payment_token: r.PaymentToken, bin: bin, bandeira: bandeira || '' };
        } finally {
            limparCamposSop();
        }
    }

    global.CheckoutCartao = { obterCredencial, ErroCartao, MSG_INSTABILIDADE };
})(window);
