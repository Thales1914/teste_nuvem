import psycopg2

def conectar_com_utf8():
    conn = psycopg2.connect(
        host="aws-0-sa-east-1.pooler.supabase.com",
        port="6543",
        dbname="postgres",
        user="postgres.norfdcltjrwwurrrogyn",
        password="omega123",
        options='-c client_encoding=UTF8'
    )
    conn.set_client_encoding('UTF8')

    with conn.cursor() as cur:
        cur.execute("SHOW client_encoding;")
        atual = cur.fetchone()[0]
        print("Client encoding:", atual)
        if atual.upper() != 'UTF8':
            raise RuntimeError(f"Client encoding incorreto: {atual}")

    return conn

if __name__ == "__main__":
    try:
        conn = conectar_com_utf8()
        print("✅ Conectado com sucesso ao Supabase com UTF8!")
        with conn.cursor() as cur:
            cur.execute("SELECT now();")
            print("Servidor diz:", cur.fetchone()[0])
    except Exception as e:
        print("❌ Falha na conexão ou encoding:", e)
