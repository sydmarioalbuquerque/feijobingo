import streamlit as st
import pandas as pd
import requests
import datetime
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email import encoders

try:
    from fpdf import FPDF
except ImportError:
    st.error("Por favor, garanta que 'fpdf2' está listado no arquivo requirements.txt no GitHub.")

# Configuração da Página
st.set_page_config(page_title="FeijoBingo 2026 - Paróquia da Madalena", layout="centered")

# CSS Responsivo para Celulares
st.markdown(
    """
    <style>
    @media (max-width: 768px) {
        .stButton > button {
            padding: 4px 2px !important;
            font-size: 11px !important;
        }
    }
    </style>
    """,
    unsafe_allow_html=True
)

# Endpoint do Google Apps Script e ID da Planilha Patrocinadores2026
URL_API = "https://script.google.com/macros/s/AKfycbyAHGNR4OoeKP3tR3xwcSFmx_8eXQcIZfekMn8o_QFPP8jZy9JjdlbT5Xh68OmVUFOD/exec"
SHEET_ID = "1XIhcv1MBsWW7ufFqSPsuj3wxrVoAcD_Dv9zJVq4kvy0" # Planilha Patrocinadores2026

CHAVE_PIX_CELULAR = "81997752112"
BENEFICIARIO_PIX = "Paróquia Nossa Senhora do Perpétuo Socorro"

# --- FUNÇÃO RESILIENTE PARA LER ABAS DO GOOGLE SHEETS ---
def ler_aba_google_sheets(nome_aba):
    url_csv = f"https://docs.google.com/spreadsheets/d/{SHEET_ID}/gviz/tq?tqx=out:csv&sheet={nome_aba}"
    try:
        df = pd.read_csv(url_csv)
        df.columns = df.columns.str.strip() # Remove espaços extras nos nomes das colunas
        return df
    except Exception as e:
        # Tenta rota alternativa sem gviz em caso de bloqueio temporário
        url_alt = f"https://docs.google.com/spreadsheets/d/{SHEET_ID}/export?format=csv&sheet={nome_aba}"
        df = pd.read_csv(url_alt)
        df.columns = df.columns.str.strip()
        return df

# --- LEITURA DINÂMICA DOS VALORES DA ABA CONFIGURACOES ---
@st.cache_data(ttl=30)
def carregar_configuracoes_precos():
    try:
        df_cfg = ler_aba_google_sheets("Configuracoes")
        df_2026 = df_cfg[df_cfg['Ano'].astype(str).str.strip() == "2026"]
        
        if not df_2026.empty:
            v_mesa_ab = float(df_2026.iloc[0]['Valor Mesa AB'])
            v_mesa_cd = float(df_2026.iloc[0]['Valor Mesa CD'])
            v_cartela = float(df_2026.iloc[0]['Valor Cartela'])
            v_combo = float(df_2026.iloc[0]['Valor Combo'])
            return v_mesa_ab, v_mesa_cd, v_cartela, v_combo
        else:
            return 50.0, 30.0, 10.0, 80.0
    except Exception:
        return 50.0, 30.0, 10.0, 80.0

VALOR_MESA_AB, VALOR_MESA_CD, VALOR_CARTELA, VALOR_COMBO = carregar_configuracoes_precos()

# Session State
if "pagamento_pendente" not in st.session_state:
    st.session_state.pagamento_pendente = False
if "dados_venda" not in st.session_state:
    st.session_state.dados_venda = {}
if "mesa_selecionada" not in st.session_state:
    st.session_state.mesa_selecionada = None

st.markdown("<h1 style='text-align: center;'>🍲 FeijoBingo 2026 🎟️</h1>", unsafe_allow_html=True)
st.markdown("<p style='text-align: center;'>Paróquia da Madalena - Venda de Mesas e Cartelas Online</p>", unsafe_allow_html=True)

modulo = st.sidebar.radio("Navegação:", ["🪑 Reserva de Mesas", "🎯 Cartelas do Bingo Online (4 Prêmios)"])

# ==========================================
# MÓDULO 1: RESERVA DE MESAS POR SETORES
# ==========================================
if modulo == "🪑 Reserva de Mesas":
    if not st.session_state.pagamento_pendente:
        st.subheader("Mapa Físico das Mesas")
        
        # IMAGEM DO MAPA FÍSICO
        URL_MAPA = "https://i.postimg.cc/s2WHBKmr/Mapa-das-Mesas.png"
        st.image(URL_MAPA, caption="Layout Oficial do FeijoBingo: Palco, Bares, Fichas, Barracas e Setores A, B, C e D", use_container_width=True)
        
        try:
            df_mesas = ler_aba_google_sheets("Mesas_FeijoBingo")
            df_mesas["ID_Mesa"] = pd.to_numeric(df_mesas["ID_Mesa"], errors='coerce').fillna(0).astype(int)
            
            # Se a coluna Status não existir por algum motivo de criação recente, inicializa
            if "Status" not in df_mesas.columns:
                df_mesas["Status"] = ""
            else:
                df_mesas["Status"] = df_mesas["Status"].fillna("").astype(str).str.strip()
        except Exception as e:
            st.error(f"Não foi possível ler a aba 'Mesas_FeijoBingo'. Certifique-se de que a planilha está compartilhada como 'Qualquer pessoa com o link pode ver'. Detalhe: {e}")
            st.stop()

        setor_escolhido = st.selectbox(
            "Selecione o Setor no Mapa:",
            ["Setor A (Frente Esquerda)", "Setor B (Frente Direita)", "Setor C (Fundo Esquerdo)", "Setor D (Fundo Direito)", "Passarela / Laterais"]
        )
        
        intervalos = {
            "Setor A (Frente Esquerda)": list(range(21, 95)),
            "Setor B (Frente Direita)": list(range(95, 172)),
            "Setor C (Fundo Esquerdo)": list(range(172, 271)),
            "Setor D (Fundo Direito)": list(range(277, 367)),
            "Passarela / Laterais": list(range(1, 21))
        }
        
        # Define o preço da mesa dinamicamente baseado na aba 'Configuracoes'
        if "Setor A" in setor_escolhido or "Setor B" in setor_escolhido:
            preco_mesa_atual = VALOR_MESA_AB
        else:
            preco_mesa_atual = VALOR_MESA_CD
        
        mesas_do_setor = intervalos[setor_escolhido]
        
        st.write(f"### Mesas do {setor_escolhido} (Valor: R$ {preco_mesa_atual:.2f}):")
        
        cols_per_row = 6
        for i in range(0, len(mesas_do_setor), cols_per_row):
            cols = st.columns(cols_per_row)
            chunk = mesas_do_setor[i:i + cols_per_row]
            for idx, id_m in enumerate(chunk):
                dados_m = df_mesas[df_mesas["ID_Mesa"] == id_m]
                
                status = ""
                if not dados_m.empty:
                    status = str(dados_m.iloc[0]["Status"]).strip().capitalize()
                
                is_livre = (status == "" or status == "Livre" or status == "Nan")
                
                with cols[idx]:
                    if is_livre:
                        if st.session_state.mesa_selecionada == id_m:
                            st.button(f"📌 {id_m:03d}", key=f"m_{id_m}", type="primary", use_container_width=True)
                        else:
                            if st.button(f"{id_m:03d}", key=f"m_{id_m}", type="secondary", use_container_width=True):
                                st.session_state.mesa_selecionada = id_m
                                st.rerun()
                    else:
                        st.button(f"❌ {id_m:03d}", key=f"m_{id_m}", disabled=True, use_container_width=True, help=f"Mesa {status}")

        if st.session_state.mesa_selecionada:
            st.success(f"Mesa Selecionada: **Nº {st.session_state.mesa_selecionada:03d}** (Valor: R$ {preco_mesa_atual:.2f})")
            with st.form("form_mesa"):
                nome = st.text_input("Nome Completo *")
                whatsapp = st.text_input("WhatsApp com DDD *")
                email = st.text_input("E-mail *")
                sub = st.form_submit_button("Avançar para o Pagamento")
                
                if sub and nome and whatsapp and email:
                    payload = {
                        "acao": "reservar_mesa_feijobingo",
                        "id_mesa": int(st.session_state.mesa_selecionada),
                        "setor": setor_escolhido,
                        "comprador_nome": nome,
                        "comprador_whatsapp": whatsapp,
                        "comprador_email": email,
                        "valor_total": float(preco_mesa_atual)
                    }
                    try:
                        res = requests.post(URL_API, json=payload)
                        if "Sucesso" in res.text or res.status_code == 200:
                            st.session_state.dados_venda = {
                                "tipo": "Mesa FeijoBingo",
                                "item": f"Mesa Nº {st.session_state.mesa_selecionada:03d} ({setor_escolhido})",
                                "nome": nome,
                                "whatsapp": whatsapp,
                                "email": email,
                                "valor": preco_mesa_atual,
                                "cod_aut": f"FB26-M{st.session_state.mesa_selecionada:03d}-{int(datetime.datetime.now().timestamp())}"
                            }
                            st.session_state.pagamento_pendente = True
                            st.session_state.mesa_selecionada = None
                            st.rerun()
                        else:
                            st.error("O servidor paroquial não processou o registro da mesa.")
                    except Exception as err:
                        st.error(f"Erro de comunicação: {err}")

# ==========================================
# MÓDULO 2: CARTELAS DE BINGO ONLINE
# ==========================================
elif modulo == "🎯 Cartelas do Bingo Online (4 Prêmios)":
    if not st.session_state.pagamento_pendente:
        st.subheader("Venda de Cartelas do Bingo Online")
        st.info("💡 Cada cartela concorre a todos os 4 prêmios principais! Mesmo quem não puder comparecer presencialmente concorrerá normalmente com o cadastro do seu nome e WhatsApp.")
        
        st.markdown(f"🎟️ **Valor Unitário da Cartela:** <span style='color:#27ae60; font-weight:bold;'>R$ {VALOR_CARTELA:.2f}</span>", unsafe_allow_html=True)
        
        qtd_cartelas = st.number_input("Quantidade de Cartelas desejadas:", min_value=1, max_value=50, value=1, step=1)
        valor_total_bingo = qtd_cartelas * VALOR_CARTELA
        
        st.markdown(f"### Total: <span style='color:#27ae60;'>R$ {valor_total_bingo:.2f}</span>", unsafe_allow_html=True)
        
        with st.form("form_bingo"):
            nome = st.text_input("Nome Completo do Titular das Cartelas *")
            whatsapp = st.text_input("WhatsApp (para contato em caso de prêmio) *")
            email = st.text_input("E-mail para envio dos números *")
            
            sub_bingo = st.form_submit_button("Gerar Cartelas e Ir para o Pix")
            
            if sub_bingo and nome and whatsapp and email:
                payload = {
                    "acao": "comprar_cartela_bingo",
                    "qtd_cartelas": int(qtd_cartelas),
                    "comprador_nome": nome,
                    "comprador_whatsapp": whatsapp,
                    "comprador_email": email,
                    "valor_total": float(valor_total_bingo)
                }
                try:
                    res = requests.post(URL_API, json=payload)
                    if "Sucesso" in res.text or res.status_code == 200:
                        st.session_state.dados_venda = {
                            "tipo": "Bingo Online",
                            "item": f"{qtd_cartelas}x Cartela(s) do Bingo Online (4 Rodadas)",
                            "nome": nome,
                            "whatsapp": whatsapp,
                            "email": email,
                            "valor": valor_total_bingo,
                            "cod_aut": f"FB26-BG-{int(datetime.datetime.now().timestamp())}"
                        }
                        st.session_state.pagamento_pendente = True
                        st.rerun()
                    else:
                        st.error("Erro interno ao gravar cartelas.")
                except Exception as err:
                    st.error(f"Erro de comunicação: {err}")

# ==========================================
# PAGAMENTO UNIFICADO VIA PIX
# ==========================================
if st.session_state.pagamento_pendente:
    venda = st.session_state.dados_venda
    st.markdown("---")
    st.subheader("📌 Finalização e Pagamento via Pix")
    st.write(f"Comprador: **{venda['nome']}** | Item: **{venda['item']}**")
    st.markdown(f"💰 **Valor Total: R$ {venda['valor']:.2f}**")
    st.code(CHAVE_PIX_CELULAR, language="text")
    
    if st.button("Voltar / Nova Operação"):
        st.session_state.pagamento_pendente = False
        st.rerun()
