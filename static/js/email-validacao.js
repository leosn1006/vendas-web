// Validação de e-mail do site inteiro (checkout, quiz e área da compra da Música, Estante).
// Mesma regra de app/web/email_validacao.py (o servidor repete a checagem e ainda confere o domínio por DNS);
// a lista de domínios é conferida pelo teste tests/web/test_email_validacao_js.py — não deixa os dois lados
// divergirem. Uso:
//   EmailValidacao.validar(email)  → { ok, motivo?: 'formato'|'sobra_apos_dominio', sugestao?: 'gmail.com' }
//   EmailValidacao.ligarSugestao(input, elementoAviso, textos?) → "Você quis dizer gmail.com?" ao sair do campo
(function () {
    const DOMINIOS_COMUNS = [
        'gmail.com', 'hotmail.com', 'outlook.com', 'hotmail.com.br', 'outlook.com.br',
        'yahoo.com.br', 'yahoo.com', 'icloud.com', 'bol.com.br', 'uol.com.br',
        'terra.com.br', 'ig.com.br', 'live.com', 'msn.com', 'oi.com.br',
        'globo.com', 'globo.com.br',
        // México: sem eles, "yahoo.com.mx" seria barrado por "começar com" yahoo.com
        'yahoo.com.mx', 'live.com.mx', 'hotmail.es', 'prodigy.net.mx',
    ];
    // Provedores com versão por país (hotmail.com.ar, outlook.com.mx): "<provedor>.<2 letras>" não é sobra.
    // O Gmail não tem — "gmail.com.br" continua barrado.
    const PROVEDORES_COM_PAIS = ['hotmail.com', 'outlook.com', 'yahoo.com', 'live.com', 'msn.com'];
    const REGEX_ESTRUTURAL =
        /^[a-zA-Z0-9._%+-]+@(?:[a-zA-Z0-9_](?:[a-zA-Z0-9_-]{0,61}[a-zA-Z0-9_])?\.)+[a-zA-Z]{2,24}$/;

    function distancia(a, b) {
        if (a === b) return 0;
        if (!a) return b.length;
        if (!b) return a.length;
        let anterior = Array.from({ length: b.length + 1 }, (_, j) => j);
        for (let i = 1; i <= a.length; i++) {
            const atual = [i];
            for (let j = 1; j <= b.length; j++) {
                const custo = a[i - 1] === b[j - 1] ? 0 : 1;
                atual[j] = Math.min(anterior[j] + 1, atual[j - 1] + 1, anterior[j - 1] + custo);
            }
            anterior = atual;
        }
        return anterior[b.length];
    }

    // ok=false só nos casos de altíssima confiança (formato, ou um domínio comum com algo a mais: gmail.comm);
    // `sugestao` com ok=true é só uma dica ("gmial.com" → "gmail.com"), nunca bloqueia.
    function validar(emailBruto) {
        const email = (emailBruto || '').trim().toLowerCase();
        if (!REGEX_ESTRUTURAL.test(email)) return { ok: false, motivo: 'formato' };
        const dominio = email.split('@')[1];
        // Igualdade exata antes do "começa com" (senão "hotmail.com.br" seria barrado por "hotmail.com").
        if (DOMINIOS_COMUNS.includes(dominio)) return { ok: true };
        // hotmail.com.ar, outlook.com.mx: versão do país (não é sobra, e não é "quase" o .com.br: sem dica)
        if (PROVEDORES_COM_PAIS.some(d => dominio.startsWith(d) && /^\.[a-z]{2}$/.test(dominio.slice(d.length)))) return { ok: true };
        for (const d of DOMINIOS_COMUNS) {
            if (dominio.startsWith(d)) return { ok: false, motivo: 'sobra_apos_dominio', sugestao: d };
        }
        let melhor = null;
        for (const d of DOMINIOS_COMUNS) {
            // Limiar 2: pega a troca de letras vizinhas ("gmial.com"); como é só dica, um falso positivo custa pouco.
            const dist = distancia(dominio, d);
            if (dist > 0 && dist <= 2 && (!melhor || dist < melhor.dist)) melhor = { dominio: d, dist };
        }
        return melhor ? { ok: true, sugestao: melhor.dominio } : { ok: true };
    }

    // "Você quis dizer gmail.com?" debaixo do campo, ao sair dele; tocar corrige. `textos.pergunta` com {dominio}
    // (cada idioma passa o seu); `aoCorrigir(novoEmail)` é chamado depois da troca.
    function ligarSugestao(input, aviso, textos, aoCorrigir) {
        const pergunta = (textos && textos.pergunta) || 'Você quis dizer {dominio}?';
        function mostrar() {
            const r = validar(input.value);
            const dominio = r.sugestao;
            if (!input.value.trim() || !dominio) { aviso.hidden = true; aviso.textContent = ''; return; }
            const [antes, depois] = pergunta.split('{dominio}');
            const link = document.createElement('a');
            link.href = '#'; link.textContent = dominio;
            link.addEventListener('click', function (ev) {
                ev.preventDefault();
                input.value = input.value.trim().split('@')[0] + '@' + dominio;
                aviso.hidden = true;
                input.dispatchEvent(new Event('input', { bubbles: true }));
                if (aoCorrigir) aoCorrigir(input.value);
            });
            aviso.textContent = '';   // (replaceChildren não existe no Safari antigo)
            aviso.appendChild(document.createTextNode(antes || ''));
            aviso.appendChild(link);
            aviso.appendChild(document.createTextNode(depois || ''));
            aviso.hidden = false;
        }
        input.addEventListener('blur', mostrar);
        input.addEventListener('input', function (ev) { if (ev.isTrusted) aviso.hidden = true; });
        return mostrar;
    }

    window.EmailValidacao = { validar, ligarSugestao, DOMINIOS_COMUNS };
})();
