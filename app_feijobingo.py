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
    st.error("Garantir 'fpdf2' no requirements.txt")

# Configuração da Página
st.set_page_config(page_title="FeijoBingo 2026 - Paróquia da Madalena", layout="centered")

# CSS Responsivo
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

# Endpoint e ID da Planilha Mestra do FeijoBingo
URL_API = "https://script.google.com/macros/s/SEU_NOVO_SCRIPT_FEIJOBINGO/exec"
SHEET_ID = "ID_DA_SUA_PLANILHA_FEIJOBINGO"

CHAVE_PIX_CELULAR = "81997752112"
BENEFICIARIO_PIX = "Paróquia Nossa Senhora do Perpétuo Socorro"

# Session State
if "pagamento_pendente" not in st.session_state:
    st.session_state.pagamento_pendente = False
if "dados_venda" not in st.session_state:
    st.session_state.dados_venda = {}
if "mesa_selecionada" not in st.session_state:
    st.session_state.mesa_selecionada = None

# Preços padrão (ou lidos da aba Parametros)
VALOR_MESA = 200.0  # Ajuste conforme o valor real
VALOR_CARTELA_BINGO = 20.0  # Dá direito às 4 rodadas do Bingo

st.markdown("<h1 style='text-align: center;'>🍲 FeijoBingo 2026 🎟️</h1>", unsafe_allow_html=True)
st.markdown("<p style='text-align: center;'>Venda de Mesas e Cartelas de Bingo Online</p>", unsafe_allow_html=True)

modulo = st.sidebar.radio("Navegação:", ["🪑 Reserva de Mesas", "🎯 Cartelas do Bingo Online (4 Prêmios)"])

# ==========================================
# MÓDULO 1: RESERVA DE MESAS POR SETORES
# ==========================================
if modulo == "🪑 Reserva de Mesas":
    if not st.session_state.pagamento_pendente:
        st.subheader("Mapa Físico das Mesas")
        
        # Exibe a imagem oficial do Mapa das Mesas enviado (Mapa das Mesas.jpg)
        URL_MAPA = "https://i.imgur.com/SEU_LINK_MAPA_FEIJOBINGO.jpg"  # Subir 'Mapa das Mesas.jpg' para o Imgur/PostImage
        st.image(URL_MAPA, caption="Layout do FeijoBingo: Palco, Bares, Fichas, Barracas e Setores A, B, C e D", use_container_width=True)
        
        try:
            url_csv = f"https://docs.google.com/spreadsheets/d/{SHEET_ID}/gviz/tq?tqx=out:csv&sheet=Mesas_FeijoBingo"
            df_mesas = pd.read_csv(url_csv)
            df_mesas["ID_Mesa"] = df_mesas["ID_Mesa"].astype(int)
            df_mesas["Status"] = df_mesas["Status"].fillna("Livre").astype(str)
        except Exception:
            st.error("Erro ao carregar o status das mesas da planilha.")
            st.stop()

        # Seleção amigável de Setor para facilitar a navegação em 366 mesas
        setor_escolhido = st.selectbox(
            "Selecione o Setor no Mapa:",
            ["Setor A (Frente Esquerda)", "Setor B (Frente Direita)", "Setor C (Fundo Esquerdo)", "Setor D (Fundo Direito)", "Passarela / Laterais"]
        )
        
        # Mapeamento dos Intervalos de Mesas por Setor conforme a imagem do PDF enviado
        intervalos = {
            "Setor A (Frente Esquerda)": list(range(21, 95)),
            "Setor B (Frente Direita)": list(range(95, 172)),
            "Setor C (Fundo Esquerdo)": list(range(172, 271)),
            "Setor D (Fundo Direito)": list(range(277, 367)),
            "Passarela / Laterais": list(range(1, 21))
        }
        
        mesas_do_setor = intervalos[setor_escolhido]
        
        st.write(f"### Mesas do {setor_escolhido} (R$ {VALOR_MESA:.2f}):")
        
        # Renderização em grid de 6 colunas
        cols_per_row = 6
        for i in range(0, len(mesas_do_setor), cols_per_row):
            cols = st.columns(cols_per_row)
            chunk = mesas_do_setor[i:i + cols_per_row]
            for idx, id_m in enumerate(chunk):
                dados_m = df_mesas[df_mesas["ID_Mesa"] == id_m]
                status = dados_m.iloc[0]["Status"].strip().capitalize() if not dados_m.empty else "Livre"
                
                with cols[idx]:
                    if status == "Livre" or status == "":
                        if st.session_state.mesa_selecionada == id_m:
                            st.button(f"📌 {id_m:03d}", key=f"m_{id_m}", type="primary", use_container_width=True)
                        else:
                            if st.button(f"{id_m:03d}", key=f"m_{id_m}", type="secondary", use_container_width=True):
                                st.session_state.mesa_selecionada = id_m
                                st.rerun()
                    else:
                        st.button(f"❌ {id_m:03d}", key=f"m_{id_m}", disabled=True, use_container_width=True)

        # Formulário de Reserva
        if st.session_state.mesa_selecionada:
            st.success(f"Mesa Selecionada: **Nº {st.session_state.mesa_selecionada:03d}**")
            with st.form("form_mesa"):
                nome = st.text_input("Nome Completo *")
                whatsapp = st.text_input("WhatsApp com DDD *")
                email = st.text_input("E-mail *")
                sub = st.form_submit_button("Avançar para o Pix")
                
                if sub and nome and whatsapp and email:
                    payload = {
                        "acao": "reservar_mesa_feijobingo",
                        "id_mesa": int(st.session_state.mesa_selecionada),
                        "comprador_nome": nome,
                        "comprador_whatsapp": whatsapp,
                        "comprador_email": email,
                        "valor_total": VALOR_MESA
                    }
                    res = requests.post(URL_API, json=payload)
                    if "Sucesso" in res.text or res.status_code == 200:
                        st.session_state.dados_venda = {
                            "tipo": "Mesa FeijoBingo",
                            "item": f"Mesa Nº {st.session_state.mesa_selecionada:03d}",
                            "nome": nome,
                            "whatsapp": whatsapp,
                            "email": email,
                            "valor": VALOR_MESA,
                            "cod_aut": f"FB26-M{st.session_state.mesa_selecionada:03d}-{int(datetime.datetime.now().timestamp())}"
                        }
                        st.session_state.pagamento_pendente = True
                        st.session_state.mesa_selecionada = None
                        st.rerun()

# ==========================================
# MÓDULO 2: CARTELAS DE BINGO ONLINE
# ==========================================
elif modulo == "🎯 Cartelas do Bingo Online (4 Prêmios)":
    if not st.session_state.pagamento_pendente:
        st.subheader("Venda de Cartelas do Bingo Online")
        st.info("💡 Cada cartela concorre a todos os 4 prêmios principais! Mesmo quem não puder comparecer presencialmente ao FeijoBingo concorrerá normalmente com o cadastro do seu nome e WhatsApp.")
        
        qtd_cartelas = st.number_input("Quantidade de Cartelas desejadas:", min_value=1, max_value=50, value=1, step=1)
        valor_total_bingo = qtd_cartelas * VALOR_CARTELA_BINGO
        
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

# ==========================================
# PAGAMENTO UNIFICADO
# ==========================================
if st.session_state.pagamento_pendente:
    venda = st.session_state.dados_venda
    st.markdown("---")
    st.subheader("📌 Finalização e Pagamento via Pix")
    st.write(f"Comprador: **{venda['nome']}** | Item: **{venda['item']}**")
    st.markdown(f"💰 **Valor Total: R$ {venda['valor']:.2f}**")
    st.code(CHAVE_PIX_CELULAR, language="text")
    
    arquivo_comprovante = st.file_uploader("Anexe o comprovante Pix aqui (*):", type=["png", "jpg", "jpeg", "pdf"])
    
    if st.button("Concluir Pedido"):
        st.success("✅ Pedido gravado com sucesso! A equipe paroquial validará seu comprovante.")
        if st.button("Novo Pedido"):
            st.session_state.pagamento_pendente = False
            st.rerun()
