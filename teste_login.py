import psycopg2
import hashlib

DB_HOST = "aws-0-sa-east-1.pooler.supabase.com"
DB_PORT = "6543"
DB_NAME = "postgres"
DB_USER = "postgres.norfdcltjrwwurrrogyn"
DB_PASS = "omega123"

def hash_senha(senha: str) -> str:
    return hashlib.sha256(senha.encode('utf-8')).hexdigest()

def testar_insercao_admin():
    conn = psycopg2.connect(
        host=DB_HOST,
        port=DB_PORT,
        dbname=DB_NAME,
        user=DB_USER,
        password=DB_PASS
    )
    with conn.cursor() as cur:
        cur.execute("DELETE FROM funcionarios WHERE cpf = 'admin'")
        cur.execute("""
            INSERT INTO funcionarios (
                cpf, codigo, nome, senha, role, empresa_id, cod_tipo, tipo, filial
            ) VALUES (
                %s, %s, %s, %s, %s, NULL, NULL, NULL, NULL
            )
        """, ('admin', 'admin', 'Administrador', hash_senha('admin123'), 'admin'))
    conn.commit()
    conn.close()
    print("✅ Usuário admin inserido com sucesso.")

def testar_login(cpf, senha):
    senha_hash = hash_senha(senha)
    conn = psycopg2.connect(
        host=DB_HOST,
        port=DB_PORT,
        dbname=DB_NAME,
        user=DB_USER,
        password=DB_PASS
    )
    with conn.cursor() as cur:
        cur.execute("SELECT * FROM funcionarios WHERE cpf = %s AND senha = %s", (cpf, senha_hash))
        user = cur.fetchone()
    conn.close()
    if user:
        print("✅ Login bem-sucedido:", user)
    else:
        print("❌ CPF ou senha inválidos.")

if __name__ == "__main__":
    testar_insercao_admin()
    testar_login("admin", "admin123")
