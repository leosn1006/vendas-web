/**
 * Gerenciamento de Modal de Comprovantes de Pagamento
 */

let comprovanteModalAtual = null;
let comprovantePathAtual = null;

function extrairPedidoId(button) {
    const pedidoId = button && button.dataset ? button.dataset.pedidoId : null;
    if (!pedidoId || isNaN(pedidoId)) {
        throw new Error('ID de pedido inválido');
    }
    return parseInt(pedidoId, 10);
}

async function buscarDadosComprovante(pedidoId) {
    const response = await fetch(`/admin/pedido/${pedidoId}/comprovante`, {
        headers: { 'Accept': 'application/json' },
        credentials: 'same-origin'
    });

    const rawBody = await response.text();
    let data = null;
    try {
        data = rawBody ? JSON.parse(rawBody) : null;
    } catch (parseError) {
        data = null;
    }

    if (!response.ok || !data || data.ok === false) {
        const htmlResponse = (rawBody || '').trim().toLowerCase().startsWith('<!doctype') || (rawBody || '').trim().toLowerCase().startsWith('<html');
        const msg = data && data.msg
            ? data.msg
            : htmlResponse
                ? 'Sessão expirada ou resposta inválida do servidor. Atualize a página e tente novamente.'
                : `Falha ao carregar comprovante (HTTP ${response.status})`;

        console.error('Falha na API de comprovante', {
            pedidoId,
            status: response.status,
            statusText: response.statusText,
            bodyPreview: (rawBody || '').slice(0, 300)
        });
        throw new Error(msg);
    }

    return data;
}

/**
 * Ação principal: abrir comprovante em nova aba
 */
async function abrirComprovanteNovaAba(button) {
    let novaAba = null;
    try {
        const pedidoId = extrairPedidoId(button);
        novaAba = window.open('', '_blank');
        if (!novaAba) {
            throw new Error('Pop-up bloqueado pelo navegador. Libere pop-ups para abrir o comprovante em nova aba.');
        }
        novaAba.opener = null;
        novaAba.document.title = 'Carregando comprovante...';
        const data = await buscarDadosComprovante(pedidoId);
        novaAba.location.href = data.path;
    } catch (error) {
        if (novaAba && !novaAba.closed) {
            novaAba.close();
        }
        console.error('Erro ao abrir comprovante em nova aba:', error);
        mostrarErroModal(error.message || 'Erro ao abrir comprovante');
        const modal = document.getElementById('comprovanteModal');
        modal.classList.add('show');
        modal.style.display = 'flex';
        document.body.classList.add('modal-open');

        let backdrop = document.querySelector('.modal-backdrop');
        if (!backdrop) {
            backdrop = document.createElement('div');
            backdrop.className = 'modal-backdrop fade show';
            document.body.appendChild(backdrop);
        }
    }
}

/**
 * Abre modal com comprovante
 */
async function abrirModalComprovante(button) {
    let pedidoId;
    try {
        pedidoId = extrairPedidoId(button);
    } catch (error) {
        console.error('Pedido ID inválido:', error);
        mostrarErroModal('ID de pedido inválido');
        return;
    }

    comprovanteModalAtual = pedidoId;

    // Abre modal imediatamente para mostrar estado de carregamento
    const modal = document.getElementById('comprovanteModal');
    document.getElementById('pedidoModalId').textContent = pedidoId;
    document.getElementById('comprovanteViewer').innerHTML = `
        <div style="display: flex; justify-content: center; align-items: center; height: 300px;">
            <div style="text-align: center; color: var(--muted); font-size: 13px;">Carregando comprovante...</div>
        </div>
    `;
    modal.classList.add('show');
    modal.style.display = 'flex';
    document.body.classList.add('modal-open');

    let backdrop = document.querySelector('.modal-backdrop');
    if (!backdrop) {
        backdrop = document.createElement('div');
        backdrop.className = 'modal-backdrop fade show';
        document.body.appendChild(backdrop);
    }

    try {
        const data = await buscarDadosComprovante(pedidoId);

        // Renderiza arquivo no viewer
        renderizarComprovante(data.path, data.extension);

    } catch (error) {
        console.error('Erro ao abrir modal:', error);
        mostrarErroModal(error.message || 'Erro ao abrir comprovante');
    }
}

function abrirComprovanteDoModalEmNovaAba() {
    if (!comprovantePathAtual) {
        return;
    }
    const novaAba = window.open(comprovantePathAtual, '_blank');
    if (novaAba) {
        novaAba.opener = null;
    } else {
        mostrarErroModal('Pop-up bloqueado pelo navegador. Libere pop-ups para abrir em nova aba.');
    }
}

/**
 * Renderiza arquivo no viewer (seguro contra XSS)
 */
function renderizarComprovante(path, extension) {
    const viewer = document.getElementById('comprovanteViewer');
    const ext = extension.toLowerCase();
    comprovantePathAtual = path;

    // Limpar conteúdo anterior
    viewer.innerHTML = '';

    if (ext === 'pdf') {
        // PDF: usar createElement para evitar XSS
        const embed = document.createElement('embed');
        embed.src = path;
        embed.type = 'application/pdf';
        embed.width = '100%';
        embed.height = '78vh';
        viewer.appendChild(embed);
    } else if (['png', 'jpg', 'jpeg', 'gif', 'webp'].includes(ext)) {
        // Imagem: usar createElement
        const img = document.createElement('img');
        img.src = path;
        img.alt = 'Comprovante';
        img.style.cssText = 'max-width: 100%; max-height: 78vh; width: auto; height: auto; border-radius: 4px;';
        viewer.appendChild(img);
    } else {
        // Tipo desconhecido: usar DOM seguro
        const container = document.createElement('div');
        container.style.cssText = 'padding: 40px 20px; color: var(--muted); text-align: center;';

        const icon = document.createElement('div');
        icon.textContent = '📄';
        icon.style.cssText = 'font-size: 48px; margin-bottom: 12px;';
        container.appendChild(icon);

        const msg = document.createElement('div');
        msg.textContent = `Tipo de arquivo não suportado: ${ext}`;
        container.appendChild(msg);

        const linkDiv = document.createElement('div');
        linkDiv.style.cssText = 'font-size: 12px; margin-top: 12px;';
        const link = document.createElement('a');
        link.href = path;
        link.target = '_blank';
        link.rel = 'noopener noreferrer';
        link.textContent = 'Abrir em nova aba →';
        link.style.cssText = 'color: var(--accent); text-decoration: none;';
        linkDiv.appendChild(link);
        container.appendChild(linkDiv);

        viewer.appendChild(container);
    }
}

/**
 * Fecha modal e retorna ao pedido
 */
function fecharModal() {
    const modal = document.getElementById('comprovanteModal');

    // Fecha modal
    modal.classList.remove('show');
    modal.style.display = 'none';
    document.body.classList.remove('modal-open');

    // Remove backdrop
    const backdrop = document.querySelector('.modal-backdrop');
    if (backdrop) {
        backdrop.remove();
    }

    // Limpar conteúdo do modal
    document.getElementById('pedidoModalId').textContent = '';
    document.getElementById('comprovanteViewer').innerHTML = '';
    comprovantePathAtual = null;

    // Scroll para pedido
    if (comprovanteModalAtual) {
        const pedidoElement = document.getElementById(`pedido-${comprovanteModalAtual}`);
        if (pedidoElement) {
            setTimeout(() => {
                pedidoElement.scrollIntoView({ behavior: 'smooth', block: 'center' });
            }, 300);
        }
        comprovanteModalAtual = null;
    }
}

/**
 * Exibe erro no modal (seguro contra XSS)
 */
function mostrarErroModal(mensagem) {
    const viewer = document.getElementById('comprovanteViewer');
    viewer.innerHTML = ''; // Limpar

    const container = document.createElement('div');
    container.style.cssText = 'padding: 40px 20px; color: #d32f2f; text-align: center;';

    const icon = document.createElement('div');
    icon.textContent = '❌';
    icon.style.cssText = 'font-size: 48px; margin-bottom: 12px;';
    container.appendChild(icon);

    const msg = document.createElement('div');
    msg.textContent = mensagem;
    container.appendChild(msg);

    viewer.appendChild(container);
}

/**
 * Gerenciamento de Modal de Detalhes do Pedido (bônus + order bump, pedidos web)
 */

let itensModalPedidoAtual = null;

const TIPO_ITEM_INFO = {
    principal: { icon: '📦', label: 'Produto principal' },
    bonus:     { icon: '🎁', label: 'Bônus' },
    bump:      { icon: '➕', label: 'Order Bump' },
};

function formatarMoeda(valor) {
    return `R$ ${Number(valor || 0).toFixed(2).replace('.', ',')}`;
}

async function buscarItensPedido(pedidoId) {
    const response = await fetch(`/admin/pedido/${pedidoId}/itens`, {
        headers: { 'Accept': 'application/json' },
        credentials: 'same-origin'
    });

    const rawBody = await response.text();
    let data = null;
    try {
        data = rawBody ? JSON.parse(rawBody) : null;
    } catch (parseError) {
        data = null;
    }

    if (!response.ok || !data || data.ok === false) {
        const htmlResponse = (rawBody || '').trim().toLowerCase().startsWith('<!doctype') || (rawBody || '').trim().toLowerCase().startsWith('<html');
        const msg = data && data.msg
            ? data.msg
            : htmlResponse
                ? 'Sessão expirada ou resposta inválida do servidor. Atualize a página e tente novamente.'
                : `Falha ao carregar detalhes (HTTP ${response.status})`;

        console.error('Falha na API de itens do pedido', {
            pedidoId,
            status: response.status,
            statusText: response.statusText,
            bodyPreview: (rawBody || '').slice(0, 300)
        });
        throw new Error(msg);
    }

    return data;
}

/**
 * Abre modal com o detalhe do pedido (produto principal + bônus + order bumps)
 */
async function abrirModalItensPedido(button) {
    let pedidoId;
    try {
        pedidoId = extrairPedidoId(button);
    } catch (error) {
        console.error('Pedido ID inválido:', error);
        mostrarErroModalItens('ID de pedido inválido');
        return;
    }

    itensModalPedidoAtual = pedidoId;

    const modal = document.getElementById('itensPedidoModal');
    document.getElementById('itensPedidoModalId').textContent = pedidoId;
    document.getElementById('itensPedidoViewer').innerHTML = `
        <div style="display: flex; justify-content: center; align-items: center; height: 150px;">
            <div style="text-align: center; color: var(--muted); font-size: 13px;">Carregando detalhes...</div>
        </div>
    `;
    modal.classList.add('show');
    modal.style.display = 'flex';
    document.body.classList.add('modal-open');

    let backdrop = document.querySelector('.modal-backdrop');
    if (!backdrop) {
        backdrop = document.createElement('div');
        backdrop.className = 'modal-backdrop fade show';
        document.body.appendChild(backdrop);
    }

    try {
        const data = await buscarItensPedido(pedidoId);
        renderizarItensPedido(data);
    } catch (error) {
        console.error('Erro ao abrir modal de itens:', error);
        mostrarErroModalItens(error.message || 'Erro ao carregar detalhes');
    }
}

/**
 * Renderiza a lista de itens estilo recibo (seguro contra XSS)
 */
function renderizarItensPedido(data) {
    const viewer = document.getElementById('itensPedidoViewer');
    viewer.innerHTML = '';

    (data.itens || []).forEach((item) => {
        const info = TIPO_ITEM_INFO[item.tipo] || { icon: '•', label: item.tipo };

        const row = document.createElement('div');
        row.className = 'recibo-item';

        const nomeWrap = document.createElement('div');
        nomeWrap.className = 'recibo-nome';

        const icon = document.createElement('span');
        icon.textContent = info.icon;
        nomeWrap.appendChild(icon);

        const nome = document.createElement('span');
        nome.textContent = item.nome || info.label;
        nomeWrap.appendChild(nome);

        const valor = document.createElement('span');
        valor.textContent = formatarMoeda(item.valor);

        row.appendChild(nomeWrap);
        row.appendChild(valor);
        viewer.appendChild(row);
    });

    const totalRow = document.createElement('div');
    totalRow.className = 'recibo-total';

    const totalLabel = document.createElement('span');
    totalLabel.textContent = 'Total';

    const totalValor = document.createElement('span');
    totalValor.textContent = formatarMoeda(data.pedido ? data.pedido.valor_pago : 0);

    totalRow.appendChild(totalLabel);
    totalRow.appendChild(totalValor);
    viewer.appendChild(totalRow);
}

/**
 * Fecha modal de itens e retorna ao pedido
 */
function fecharModalItens() {
    const modal = document.getElementById('itensPedidoModal');

    modal.classList.remove('show');
    modal.style.display = 'none';
    document.body.classList.remove('modal-open');

    const backdrop = document.querySelector('.modal-backdrop');
    if (backdrop) {
        backdrop.remove();
    }

    document.getElementById('itensPedidoModalId').textContent = '';
    document.getElementById('itensPedidoViewer').innerHTML = '';

    if (itensModalPedidoAtual) {
        const pedidoElement = document.getElementById(`pedido-${itensModalPedidoAtual}`);
        if (pedidoElement) {
            setTimeout(() => {
                pedidoElement.scrollIntoView({ behavior: 'smooth', block: 'center' });
            }, 300);
        }
        itensModalPedidoAtual = null;
    }
}

/**
 * Exibe erro no modal de itens (seguro contra XSS)
 */
function mostrarErroModalItens(mensagem) {
    const viewer = document.getElementById('itensPedidoViewer');
    viewer.innerHTML = '';

    const container = document.createElement('div');
    container.style.cssText = 'padding: 40px 20px; color: #d32f2f; text-align: center;';

    const icon = document.createElement('div');
    icon.textContent = '❌';
    icon.style.cssText = 'font-size: 48px; margin-bottom: 12px;';
    container.appendChild(icon);

    const msg = document.createElement('div');
    msg.textContent = mensagem;
    container.appendChild(msg);

    viewer.appendChild(container);
}

/**
 * Fecha modais ao clicar fora (backdrop) ou pressionar Escape
 */
document.addEventListener('DOMContentLoaded', function() {
    const modais = [
        { modal: document.getElementById('comprovanteModal'), fechar: fecharModal },
        { modal: document.getElementById('itensPedidoModal'), fechar: fecharModalItens },
    ];

    modais.forEach(({ modal, fechar }) => {
        if (!modal) {
            return;
        }

        modal.addEventListener('click', function(e) {
            if (e.target === modal) {
                fechar();
            }
        });

        document.addEventListener('keydown', function(e) {
            if (e.key === 'Escape' && modal.classList.contains('show')) {
                fechar();
            }
        });
    });
});
