/**
 * Gerenciamento de Modal de Comprovantes de Pagamento
 */

let comprovanteModalAtual = null;

/**
 * Abre modal com comprovante
 */
async function abrirModalComprovante(button) {
    // Extrair ID do data-attribute (seguro contra injeção)
    const pedidoId = button.dataset.pedidoId;
    if (!pedidoId || isNaN(pedidoId)) {
        console.error('Pedido ID inválido:', pedidoId);
        mostrarErroModal('ID de pedido inválido');
        return;
    }

    comprovanteModalAtual = parseInt(pedidoId);

    // Abre modal imediatamente para mostrar estado de carregamento
    const modal = document.getElementById('comprovanteModal');
    document.getElementById('pedidoModalId').textContent = pedidoId;
    document.getElementById('comprovanteViewer').innerHTML = `
        <div style="display: flex; justify-content: center; align-items: center; height: 300px;">
            <div style="text-align: center; color: var(--muted); font-size: 13px;">Carregando comprovante...</div>
        </div>
    `;
    modal.classList.add('show');
    modal.style.display = 'block';
    document.body.classList.add('modal-open');

    let backdrop = document.querySelector('.modal-backdrop');
    if (!backdrop) {
        backdrop = document.createElement('div');
        backdrop.className = 'modal-backdrop fade show';
        document.body.appendChild(backdrop);
    }

    try {
        // Fetch comprovante info
        const response = await fetch(`/admin/pedido/${pedidoId}/comprovante`, {
            headers: { 'Accept': 'application/json' },
            credentials: 'same-origin'
        });

        const rawBody = await response.text();
        let data = null;
        try {
            data = rawBody ? JSON.parse(rawBody) : null;
        } catch (parseError) {
            // Resposta pode ser HTML (ex.: redirect/login) ou texto simples
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

            mostrarErroModal(msg);
            return;
        }

        // Renderiza arquivo no viewer
        renderizarComprovante(data.path, data.extension);

    } catch (error) {
        console.error('Erro ao abrir modal:', error);
        mostrarErroModal('Erro ao abrir comprovante');
    }
}

/**
 * Renderiza arquivo no viewer (seguro contra XSS)
 */
function renderizarComprovante(path, extension) {
    const viewer = document.getElementById('comprovanteViewer');
    const ext = extension.toLowerCase();

    // Limpar conteúdo anterior
    viewer.innerHTML = '';

    if (ext === 'pdf') {
        // PDF: usar createElement para evitar XSS
        const embed = document.createElement('embed');
        embed.src = path;
        embed.type = 'application/pdf';
        embed.width = '100%';
        embed.height = '600px';
        viewer.appendChild(embed);
    } else if (['png', 'jpg', 'jpeg', 'gif', 'webp'].includes(ext)) {
        // Imagem: usar createElement
        const img = document.createElement('img');
        img.src = path;
        img.alt = 'Comprovante';
        img.style.cssText = 'max-width: 100%; max-height: 600px; border-radius: 4px;';
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
 * Fecha modal ao clicar fora (backdrop)
 */
document.addEventListener('DOMContentLoaded', function() {
    const modal = document.getElementById('comprovanteModal');

    if (modal) {
        modal.addEventListener('click', function(e) {
            if (e.target === modal) {
                fecharModal();
            }
        });

        // Tecla Escape para fechar
        document.addEventListener('keydown', function(e) {
            if (e.key === 'Escape' && modal.classList.contains('show')) {
                fecharModal();
            }
        });
    }
});
