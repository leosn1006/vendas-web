#!/usr/bin/env python3
"""
Script para testar a conexão com o banco de dados e verificar se as tabelas foram criadas.
"""
import sys
import os

# Adicionar o diretório app ao path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'app'))

from database import db, get_produtos_ativos
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def verificar_conexao():
    """Verifica se a conexão com o banco está OK."""
    print("=" * 60)
    print("🔍 Testando Conexão com Banco de Dados")
    print("=" * 60)

    if db.test_connection():
        print("✅ Conexão com banco de dados OK!\n")
        return True
    else:
        print("❌ Erro ao conectar com banco de dados!\n")
        return False


def verificar_tabelas():
    """Verifica se as tabelas foram criadas."""
    print("=" * 60)
    print("🗄️  Verificando Tabelas")
    print("=" * 60)

    tabelas = ['produtos', 'estado_pedidos', 'pedidos', 'mensagens_pedidos']

    try:
        with db.get_cursor() as cursor:
            cursor.execute("SHOW TABLES")
            tabelas_existentes = [table['Tables_in_vendasdb'] for table in cursor.fetchall()]

            print(f"\nTabelas encontradas: {len(tabelas_existentes)}")
            for tabela in tabelas_existentes:
                status = "✅" if tabela in tabelas else "⚠️"
                print(f"  {status} {tabela}")

            # Verificar se todas as tabelas necessárias existem
            tabelas_faltando = set(tabelas) - set(tabelas_existentes)
            if tabelas_faltando:
                print(f"\n❌ Tabelas faltando: {', '.join(tabelas_faltando)}")
                return False
            else:
                print("\n✅ Todas as tabelas necessárias existem!")
                return True

    except Exception as e:
        print(f"\n❌ Erro ao verificar tabelas: {e}")
        return False


def verificar_dados():
    """Verifica se há dados nas tabelas."""
    print("\n" + "=" * 60)
    print("📊 Verificando Dados")
    print("=" * 60)

    try:
        # Verificar produtos
        produtos = get_produtos_ativos()
        print(f"\n✅ Produtos cadastrados: {len(produtos)}")
        for produto in produtos:
            print(f"  - {produto['nome']}: R$ {produto['preco']:.2f}")

        # Verificar estados de pedidos
        with db.get_cursor() as cursor:
            cursor.execute("SELECT COUNT(*) as total FROM estado_pedidos")
            total_estados = cursor.fetchone()['total']
            print(f"\n✅ Estados de pedidos: {total_estados}")

            cursor.execute("SELECT id, descricao FROM estado_pedidos ORDER BY id")
            estados = cursor.fetchall()
            for estado in estados:
                print(f"  {estado['id']}. {estado['descricao']}")

        # Verificar pedidos
        with db.get_cursor() as cursor:
            cursor.execute("SELECT COUNT(*) as total FROM pedidos")
            total_pedidos = cursor.fetchone()['total']
            print(f"\n📦 Total de pedidos: {total_pedidos}")

            if total_pedidos > 0:
                cursor.execute("""
                    SELECT p.id, p.contact_name, ep.descricao as estado, p.data_pedido
                    FROM pedidos p
                    JOIN estado_pedidos ep ON p.estado_pedido_id = ep.id
                    ORDER BY p.data_pedido DESC
                    LIMIT 5
                """)
                pedidos = cursor.fetchall()
                print("\n  Últimos pedidos:")
                for pedido in pedidos:
                    print(f"  - #{pedido['id']} | {pedido['contact_name']} | {pedido['estado']} | {pedido['data_pedido']}")

        return True

    except Exception as e:
        print(f"\n❌ Erro ao verificar dados: {e}")
        return False


def main():
    """Função principal."""
    print("\n")
    print("🚀 " + "=" * 56 + " 🚀")
    print("   VERIFICAÇÃO DO BANCO DE DADOS - VENDAS WEB")
    print("🚀 " + "=" * 56 + " 🚀")
    print()

    # Verificar variáveis de ambiente
    variaveis = ['DB_HOST', 'DB_PORT', 'DB_NAME', 'DB_USER', 'DB_PASSWORD']
    print("🔧 Variáveis de Ambiente:")
    for var in variaveis:
        valor = os.getenv(var, 'NÃO CONFIGURADA')
        if var == 'DB_PASSWORD':
            valor = '***' if valor != 'NÃO CONFIGURADA' else valor
        print(f"  {var}: {valor}")
    print()

    # Executar verificações
    resultados = []

    resultados.append(("Conexão", verificar_conexao()))
    resultados.append(("Tabelas", verificar_tabelas()))
    resultados.append(("Dados", verificar_dados()))

    # Resumo
    print("\n" + "=" * 60)
    print("📋 RESUMO")
    print("=" * 60)

    for nome, sucesso in resultados:
        status = "✅ OK" if sucesso else "❌ ERRO"
        print(f"  {nome:.<30} {status}")

    print("\n" + "=" * 60)

    # Resultado final
    if all(r[1] for r in resultados):
        print("🎉 Banco de dados configurado corretamente!")
        print("=" * 60)
        return 0
    else:
        print("⚠️  Há problemas com o banco de dados. Verifique os logs acima.")
        print("=" * 60)
        return 1


if __name__ == "__main__":
    sys.exit(main())
