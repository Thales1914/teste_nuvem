import psycopg2
import psycopg2.extras
import pandas as pd
from datetime import datetime, time
from config import FUSO_HORARIO, HORARIOS_PADRAO, TOLERANCIA_MINUTOS
import hashlib
from contextlib import contextmanager
import numpy as np
import io
import streamlit as st

try:
    DATABASE_URL = st.secrets["postgres"]["db_url"]
except Exception:

    DATABASE_URL = "postgres://postgres:Omega2894@localhost:5432/ponto_db"

@contextmanager
def get_db_connection():
    conn = psycopg2.connect(DATABASE_URL)
    try:
        yield conn
    finally:
        conn.close()

def _hash_senha(senha: str) -> str:
    return hashlib.sha256(senha.encode('utf-8')).hexdigest()

def init_db():
    with get_db_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute('CREATE TABLE IF NOT EXISTS empresas (id SERIAL PRIMARY KEY, nome_empresa TEXT NOT NULL UNIQUE)')
            cursor.execute('CREATE TABLE IF NOT EXISTS funcionarios (codigo TEXT PRIMARY KEY, nome TEXT NOT NULL, senha TEXT NOT NULL, role TEXT NOT NULL, empresa_id INTEGER, FOREIGN KEY (empresa_id) REFERENCES empresas (id))')
            cursor.execute('CREATE TABLE IF NOT EXISTS registros (id TEXT PRIMARY KEY, codigo_funcionario TEXT NOT NULL, nome TEXT NOT NULL, data TEXT NOT NULL, hora TEXT NOT NULL, descricao TEXT NOT NULL, diferenca_min INTEGER NOT NULL, observacao TEXT, FOREIGN KEY (codigo_funcionario) REFERENCES funcionarios (codigo))')
            
            cursor.execute("SELECT COUNT(*) FROM empresas")
            if cursor.fetchone()[0] == 0:
                initial_empresas = [('Ômega Barroso',), ('Ômega Matriz',), ('Ômega Cariri',), ('Ômega Sobral',)]
                cursor.executemany("INSERT INTO empresas (nome_empresa) VALUES (%s)", initial_empresas)

            cursor.execute("SELECT COUNT(*) FROM funcionarios")
            if cursor.fetchone()[0] == 0:
                initial_users = [('admin', 'Administrador', _hash_senha('admin123'), 'admin', None)]
                cursor.executemany("INSERT INTO funcionarios (codigo, nome, senha, role, empresa_id) VALUES (%s, %s, %s, %s, %s)", initial_users)
        conn.commit()

@st.cache_data
def ler_empresas():
    with get_db_connection() as conn:
        return pd.read_sql_query("SELECT id, nome_empresa FROM empresas ORDER BY nome_empresa", conn)

@st.cache_data
def ler_funcionarios_df():
    with get_db_connection() as conn:
        query = "SELECT f.codigo, f.nome, f.role, f.empresa_id, e.nome_empresa FROM funcionarios f LEFT JOIN empresas e ON f.empresa_id = e.id"
        return pd.read_sql_query(query, conn)

def verificar_login(codigo, senha):
    senha_hash = _hash_senha(senha)
    user = None
    with get_db_connection() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cursor:
            cursor.execute("SELECT * FROM funcionarios WHERE codigo = %s AND senha = %s", (codigo, senha_hash))
            user = cursor.fetchone()
    return (dict(user), None) if user else (None, "Código ou senha inválidos.")

def obter_proximo_evento(codigo):
    hoje_str = datetime.now(FUSO_HORARIO).strftime("%Y-%m-%d")
    with get_db_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute("SELECT COUNT(*) FROM registros WHERE codigo_funcionario = %s AND data = %s", (codigo, hoje_str))
            num_pontos = cursor.fetchone()[0]
    eventos = list(HORARIOS_PADRAO.keys())
    return eventos[num_pontos] if num_pontos < len(eventos) else "Jornada Finalizada"

def bater_ponto(codigo, nome):
    agora = datetime.now(FUSO_HORARIO)
    proximo_evento = obter_proximo_evento(codigo)
    if proximo_evento == "Jornada Finalizada":
        return "Sua jornada de hoje já foi completamente registada.", "warning"
    hora_prevista = HORARIOS_PADRAO[proximo_evento]
    datetime_previsto = agora.replace(hour=hora_prevista.hour, minute=hora_prevista.minute, second=0, microsecond=0)
    diff_bruta = round((agora - datetime_previsto).total_seconds() / 60)
    diff_final = 0 if abs(diff_bruta) <= TOLERANCIA_MINUTOS else diff_bruta - TOLERANCIA_MINUTOS if diff_bruta > 0 else diff_bruta + TOLERANCIA_MINUTOS
    novo_reg = (f"{codigo}-{agora.isoformat()}", codigo, nome, agora.strftime("%Y-%m-%d"), agora.strftime("%H:%M:%S"), proximo_evento, diff_final, "")
    with get_db_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute("INSERT INTO registros (id, codigo_funcionario, nome, data, hora, descricao, diferenca_min, observacao) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)", novo_reg)
        conn.commit()
    msg_extra = ""
    if diff_final != 0:
        msg_extra = f" ({diff_final} min de atraso)" if diff_final > 0 else f" ({-diff_final} min de adiantamento)"
    status_final = " (em ponto)"
    if diff_final != 0:
        status_final = ""
    elif diff_bruta != 0:
        status_final = " (dentro da tolerância, registrado como 'em ponto')"
    return f"'{proximo_evento}' registado para {nome} às {agora.strftime('%H:%M:%S')}{msg_extra}{status_final}.", "success"

@st.cache_data
def ler_registros_df():
    with get_db_connection() as conn:
        query = "SELECT r.id, r.codigo_funcionario, r.nome, r.data, r.hora, r.descricao, r.diferenca_min, r.observacao, e.nome_empresa FROM registros r JOIN funcionarios f ON r.codigo_funcionario = f.codigo LEFT JOIN empresas e ON f.empresa_id = e.id"
        df = pd.read_sql_query(query, conn)
    return df.rename(columns={'id': 'ID', 'codigo_funcionario': 'Código', 'nome': 'Nome', 'data': 'Data', 'hora': 'Hora', 'descricao': 'Descrição', 'diferenca_min': 'Diferença (min)', 'observacao': 'Observação', 'nome_empresa': 'Empresa'})

def atualizar_registro(id_registro, novo_horario=None, nova_observacao=None):
    try:
        with get_db_connection() as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cursor:
                if nova_observacao is not None:
                    cursor.execute("UPDATE registros SET observacao = %s WHERE id = %s", (nova_observacao, id_registro))
                if novo_horario is not None:
                    novo_obj = datetime.strptime(novo_horario, "%H:%M:%S").time()
                    cursor.execute("SELECT descricao, data FROM registros WHERE id = %s", (id_registro,))
                    row = cursor.fetchone()
                    if row:
                        hora_prevista = HORARIOS_PADRAO.get(row['descricao'])
                        if hora_prevista:
                            dt_reg = datetime.strptime(row['data'], "%Y-%m-%d")
                            dt_previsto = dt_reg.replace(hour=hora_prevista.hour, minute=hora_prevista.minute)
                            dt_novo = dt_reg.replace(hour=novo_obj.hour, minute=novo_obj.minute, second=novo_obj.second)
                            diff_bruta = round((dt_novo - dt_previsto).total_seconds() / 60)
                            diff_final = 0 if abs(diff_bruta) <= TOLERANCIA_MINUTOS else diff_bruta - TOLERANCIA_MINUTOS if diff_bruta > 0 else diff_bruta + TOLERANCIA_MINUTOS
                            cursor.execute("UPDATE registros SET hora = %s, diferenca_min = %s WHERE id = %s", (novo_horario, diff_final, id_registro))
            conn.commit()
    except ValueError:
        return "Formato de hora inválido. Use HH:MM:SS.", "error"
    except psycopg2.Error as e:
        return f"Erro no banco de dados: {e}", "error"
    return "Registro atualizado com sucesso.", "success"

def adicionar_funcionario(codigo, nome, senha, empresa_id):
    if not all([codigo, nome, senha, empresa_id]):
        return "Todos os campos são obrigatórios.", "error"
    try:
        with get_db_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute("SELECT codigo FROM funcionarios WHERE codigo = %s", (codigo,))
                if cursor.fetchone():
                    return f"O código '{codigo}' já está em uso.", "warning"
                senha_hash = _hash_senha(senha)
                cursor.execute("INSERT INTO funcionarios (codigo, nome, senha, role, empresa_id) VALUES (%s, %s, %s, %s, %s)", (codigo, nome, senha_hash, 'employee', empresa_id))
            conn.commit()
    except psycopg2.Error as e:
        return f"Erro no banco de dados: {e}", "error"
    return f"Funcionário '{nome}' adicionado com sucesso!", "success"

def importar_funcionarios_em_massa(df_funcionarios, empresa_id):
    novos_funcionarios, erros, sucesso_count, ignorados_count = [], [], 0, 0
    codigos_existentes = ler_funcionarios_df()['codigo'].tolist()
    colunas_necessarias = ['MATRICULA', 'COLABORADOR', 'SENHA']
    if not all(col in df_funcionarios.columns for col in colunas_necessarias):
        return 0, 0, [f"Erro Crítico: Verifique se as colunas {colunas_necessarias} existem no arquivo."]
    for index, row in df_funcionarios.iterrows():
        try:
            codigo, nome_completo, senha_texto = str(row['MATRICULA']).strip(), str(row['COLABORADOR']).strip(), str(row['SENHA']).strip()
            if codigo in codigos_existentes:
                ignorados_count += 1
                continue
            if not all([codigo, nome_completo, senha_texto]):
                erros.append(f"Linha {index+2}: Dados incompletos.")
                continue
            novos_funcionarios.append((codigo, nome_completo, _hash_senha(senha_texto), 'employee', empresa_id))
            codigos_existentes.append(codigo)
        except Exception as e:
            erros.append(f"Linha {index+2}: Erro - {e}")
    if novos_funcionarios:
        try:
            with get_db_connection() as conn:
                with conn.cursor() as cursor:
                    cursor.executemany("INSERT INTO funcionarios (codigo, nome, senha, role, empresa_id) VALUES (%s, %s, %s, %s, %s)", novos_funcionarios)
                conn.commit()
                sucesso_count = len(novos_funcionarios)
        except psycopg2.Error as e:
            erros.append(f"Erro geral no banco de dados: {e}")
    return sucesso_count, ignorados_count, erros

def _formatar_timedelta(td):
    if pd.isnull(td): return "00:00"
    total_seconds = int(td.total_seconds())
    hours, remainder = divmod(total_seconds, 3600)
    minutes, _ = divmod(remainder, 60)
    return f"{hours:02d}:{minutes:02d}"

def gerar_relatorio_organizado_df(df_registros: pd.DataFrame) -> pd.DataFrame:
    if df_registros.empty: return pd.DataFrame()
    df = df_registros.copy()
    df['Descrição'] = df['Descrição'].replace({"Início do Expediente": "Entrada", "Fim do Expediente": "Saída"})
    df_pivot = df.pivot_table(index=['Data', 'Código', 'Nome', 'Empresa'], columns='Descrição', values='Hora', aggfunc='first').reset_index()
    df_obs = df.dropna(subset=['Observação']).groupby(['Data', 'Código'])['Observação'].apply(lambda x: ' | '.join(x.unique())).reset_index()
    df_final = pd.merge(df_pivot, df_obs, on=['Data', 'Código'], how='left').fillna({'Observação': ''})
    for evento in ['Entrada', 'Saída']:
        if evento not in df_final.columns: df_final[evento] = np.nan
        df_final[evento] = pd.to_datetime(df_final[evento], format='%H:%M:%S', errors='coerce').dt.time
    dt_entrada = pd.to_datetime(df_final['Data'].astype(str) + ' ' + df_final['Entrada'].astype(str), errors='coerce')
    dt_saida = pd.to_datetime(df_final['Data'].astype(str) + ' ' + df_final['Saída'].astype(str), errors='coerce')
    df_final['Total Horas Trabalhadas'] = (dt_saida - dt_entrada).apply(_formatar_timedelta)
    colunas = ['Data', 'Código', 'Nome', 'Empresa', 'Entrada', 'Saída', 'Total Horas Trabalhadas', 'Observação']
    for col in colunas:
        if col not in df_final.columns: df_final[col] = 'N/A'
    df_final = df_final[colunas]
    df_final.rename(columns={'Código': 'Código do Funcionário', 'Nome': 'Nome do Funcionário'}, inplace=True)
    df_final['Data'] = pd.to_datetime(df_final['Data']).dt.strftime('%d/%m/%Y')
    return df_final

def gerar_arquivo_excel(df_organizado, df_bruto):
    output_buffer = io.BytesIO()
    with pd.ExcelWriter(output_buffer, engine='openpyxl') as writer:
        df_organizado.to_excel(writer, sheet_name='Relatório Diário', index=False)
        df_bruto.to_excel(writer, sheet_name='Log de Eventos (Bruto)', index=False)
        for sheet_name in writer.sheets:
            worksheet = writer.sheets[sheet_name]
            for column in worksheet.columns:
                max_length = 0
                column_letter = column[0].column_letter
                for cell in column:
                    try:
                        if len(str(cell.value)) > max_length:
                            max_length = len(str(cell.value))
                    except: pass
                worksheet.column_dimensions[column_letter].width = (max_length + 2)
    output_buffer.seek(0)
    return output_buffer