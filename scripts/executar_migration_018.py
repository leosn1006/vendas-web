#!/usr/bin/env python3
"""
Script para executar a migration 018 - Renomear template WhatsApp
"""
import sys
import os

# Adiciona o diretório app ao path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'app'))

from database import db

def executar_migration():
    """Executa a migration 018"""
    print("=" * 80)
    print("Migration 018: Renomear template 'entrega_pedido_venda' para 'entrega_pedido'")
    print("=" * 80)

    # Verifica estado antes
    print("\n1. Estado ANTES da migration:")
    resultado_antes = db.execute_query(
        "SELECT id, produto_id, fluxo, ordem, acao, mensagem AS template_name, param1, param2 "
        "FROM acoes_fluxo_produto WHERE acao = 'enviar_produto_whatsapp'",
        fetch_all=True
    )
    if resultado_antes:
        for row in resultado_antes:
            print(f"   ID {row['id']}: template='{row['template_name']}', param1='{row['param1']}', param2='{row['param2']}'")
    else:
        print("   Nenhuma ação encontrada.")

    # Executa o UPDATE
    print("\n2. Executando UPDATE...")
    db.execute_query(
        "UPDATE acoes_fluxo_produto "
        "SET mensagem = 'entrega_pedido' "
        "WHERE mensagem = 'entrega_pedido_venda' AND acao = 'enviar_produto_whatsapp'"
    )
    print("   ✅ UPDATE executado com sucesso!")

    # Verifica estado depois
    print("\n3. Estado DEPOIS da migration:")
    resultado_depois = db.execute_query(
        "SELECT id, produto_id, fluxo, ordem, acao, mensagem AS template_name, param1, param2 "
        "FROM acoes_fluxo_produto WHERE acao = 'enviar_produto_whatsapp'",
        fetch_all=True
    )
    if resultado_depois:
        for row in resultado_depois:
            print(f"   ID {row['id']}: template='{row['template_name']}', param1='{row['param1']}', param2='{row['param2']}'")
    else:
        print("   Nenhuma ação encontrada.")

    print("\n" + "=" * 80)
    print("✅ Migration 018 concluída com sucesso!")
    print("=" * 80)

if __name__ == "__main__":
    try:
        executar_migration()
    except Exception as e:
        print(f"\n❌ Erro ao executar migration: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
