#!/bin/bash
# Script de Refatoração Automática - FASE 1
# Executa as correções críticas em 30 minutos

set -e  # Sair em caso de erro

echo "🔧 Iniciando Refatoração FASE 1..."
echo ""

# Backup antes de começar
echo "📦 Criando backup..."
timestamp=$(date +%Y%m%d_%H%M%S)
backup_dir="backup_$timestamp"
mkdir -p "$backup_dir"
cp -r app "$backup_dir/"
echo "✅ Backup criado em: $backup_dir"
echo ""

# 1. Renomear arquivos
echo "📝 Renomeando arquivos..."
[ -f "app/requisitos.txt" ] && mv app/requisitos.txt requirements.txt && echo "  ✅ requisitos.txt → requirements.txt"
[ -f "app/constante.py" ] && mv app/constante.py app/config.py && echo "  ✅ constante.py → config.py"
[ -f "app/Gerar_token.py" ] && mv app/Gerar_token.py app/gerar_token.py && echo "  ✅ Gerar_token.py → gerar_token.py"
echo ""

# 2. Criar nova estrutura de pastas
echo "📁 Criando estrutura de pastas..."
mkdir -p app/templates
mkdir -p static/images
echo "  ✅ app/templates/ criado"
echo "  ✅ static/images/ criado"
echo ""

# 3. Mover HTMLs
echo "📄 Movendo templates HTML..."
for html in app/*.html; do
    if [ -f "$html" ]; then
        filename=$(basename "$html")
        mv "$html" "app/templates/$filename"
        echo "  ✅ $filename → app/templates/"
    fi
done
echo ""

# 4. Mover imagens
echo "🖼️  Movendo imagens..."
if [ -d "app/imagens" ]; then
    mv app/imagens/* static/images/ 2>/dev/null || true
    rmdir app/imagens 2>/dev/null || true
    echo "  ✅ imagens/ → static/images/"
fi
echo ""

# 5. Atualizar .gitignore
echo "🚫 Atualizando .gitignore..."
cat >> .gitignore << 'EOL'

# Python
__pycache__/
*.py[cod]
*$py.class
*.so
.Python

# Ambientes
.env
venv/
env/
ENV/

# Mac
.DS_Store

# IDEs
.vscode/
.idea/
*.swp
*.swo

# Backups
backup_*/
EOL
echo "  ✅ .gitignore atualizado"
echo ""

# 6. Atualizar imports em arquivos Python
echo "🔄 Atualizando imports..."

# Atualizar imports de constante → config
if [ -f "app/enviar_mensagem_whatsApp.py" ]; then
    sed -i.bak 's/from constante import/from config import/g' app/enviar_mensagem_whatsApp.py
    rm app/enviar_mensagem_whatsApp.py.bak 2>/dev/null || true
    echo "  ✅ enviar_mensagem_whatsApp.py atualizado"
fi

# 7. Atualizar app.py para usar templates
echo "🔧 Atualizando app.py para usar render_template..."
# (Isso precisará ser feito manualmente ou com um script Python mais sofisticado)
echo "  ⚠️  app.py precisa ser atualizado manualmente"
echo "      Trocar send_file('arquivo.html') por render_template('arquivo.html')"
echo ""

# 8. Atualizar Dockerfile
echo "🐳 Atualizando Dockerfile..."
if [ -f "Dockerfile" ]; then
    sed -i.bak 's|app/requisitos.txt|requirements.txt|g' Dockerfile
    rm Dockerfile.bak 2>/dev/null || true
    echo "  ✅ Dockerfile atualizado"
fi
echo ""

# 9. Limpar arquivos de cache
echo "🧹 Limpando cache..."
find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
find . -type f -name "*.pyc" -delete 2>/dev/null || true
find . -type f -name ".DS_Store" -delete 2>/dev/null || true
echo "  ✅ Cache limpo"
echo ""

# 10. Criar documentação
echo "📚 Organizando documentação..."
mkdir -p docs
[ -f "WEBHOOK_WHATSAPP.md" ] && mv WEBHOOK_WHATSAPP.md docs/ && echo "  ✅ WEBHOOK_WHATSAPP.md → docs/"
[ -f "app/SEGURANCA_README.md" ] && mv app/SEGURANCA_README.md docs/SEGURANCA.md && echo "  ✅ SEGURANCA_README.md → docs/SEGURANCA.md"
echo ""

# 11. Criar scripts/
echo "📜 Organizando scripts..."
mkdir -p scripts
[ -f "app/gerar_token.py" ] && mv app/gerar_token.py scripts/ && echo "  ✅ gerar_token.py → scripts/"
[ -f "app/exemplo_seguranca.py" ] && mv app/exemplo_seguranca.py scripts/ && echo "  ✅ exemplo_seguranca.py → scripts/"
echo ""

echo "✅ FASE 1 concluída com sucesso!"
echo ""
echo "📋 Próximos passos manuais:"
echo "  1. Atualizar app.py:"
echo "     - Trocar Flask(__name__) por Flask(__name__, template_folder='templates')"
echo "     - Trocar send_file() por render_template()"
echo ""
echo "  2. Atualizar imports de config.py em todos os arquivos"
echo ""
echo "  3. Testar a aplicação:"
echo "     docker compose down"
echo "     docker compose up -d --build"
echo "     docker compose logs -f app"
echo ""
echo "  4. Se tudo funcionar, remover backup:"
echo "     rm -rf $backup_dir"
echo ""
