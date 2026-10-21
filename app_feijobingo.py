import streamlit as st
import pandas as pd
import requests
import datetime
import smtplib
import unicodedata
import streamlit.components.v1 as components
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email import encoders

try:
    from fpdf import FPDF
except ImportError:
    st.error("Por favor, garanta que 'fpdf2' está listado no arquivo requirements.txt no GitHub.")

# --- 1. CONFIGURAÇÃO DA PÁGINA E ÍCONE DA IGREJA ---
URL_LOGO_IGREJA = "https://i.imgur.com/k3okz8x.png"

st.set_page_config(
    page_title="FeijoBingo 2026 - Paróquia da Madalena", 
    page_icon=URL_LOGO_IGREJA, 
    layout="centered"
)

# --- INJEÇÃO DE HTML PARA LIBERAR ZOOM EM DISPOSITIVOS MÓVEIS ---
components.html(
    """
    <script>
        var meta = document.createElement('meta');
        meta.name = 'viewport';
        meta.content = 'width=device-width, initial-scale=1.0, maximum-scale=5.0, user-scalable=yes';
        document.getElementsByTagName('head')[0].appendChild(meta);
    </script>
    """,
    height=0,
)

# --- INJEÇÃO DE CSS RESPONSIVO LIMPO (SEM TEXTO VISÍVEL NA TELA) ---
st.markdown(
    """
    <style>
    .block-container {
        padding-left: 0.8rem !important;
        padding-right: 0.8rem !important;
        max-width: 100% !important;
    }
    
    [data-testid="stHorizontalBlock"] {
        display: flex !important;
        flex-direction: row !important;
        flex-wrap: nowrap !important;
        gap: 3px !important;
    }
    
    [data-testid="column"] {
        min-width: 0px !important;
        flex: 1 1 0% !important;
    }
    
    .stButton > button {
        padding: 6px 1px !important;
        font-size: 11px !important;
        height: auto !important;
        width: 100% !important;
        border-radius: 4px !important;
    }

    @media (min-width: 769px) {
        .stButton > button {
            font-size: 13px !important;
            padding: 8px !important;
        }
    }
    </style>
    """,
    unsafe_allow_html=True
)

# Endpoint do Google Apps Script e ID da Planilha Patrocinadores2026
URL_API = "https://script.google.com/macros/s/AKfycbyAHGNR4OoeKP3tR3xwcSFmx_8eXQcIZfekMn8o_QFPP8jZy9JjdlbT5Xh68OmVUFOD/exec"
SHEET_ID = "1XIhcv1MBsWW7ufFqSPsuj3wxrVoAcD_Dv9zJVq4kvy0"

CHAVE_PIX_CELULAR = "81997752112"
BENEFICIARIO_PIX = "PAROQUIA NOSSA SENHORA DO PERPETUO SOCORRO"
URL_CARTAO_CREDITO = "https://www.mercadopago.com.br"

# --- REMOÇÃO RIGOROSA DE ACENTOS PARA PADRÃO EMV ---
def remover_acentos(texto):
    return ''.join(
        c for c in unicodedata.normalize('NFD', str(texto))
        if unicodedata.category(c) != 'Mn'
    )

# --- GERADOR DE PIX EMV (BR CODE) 100% HOMOLOGADO BANCO CENTRAL ---
def gerar_payload_pix(chave, nome, valor, cidade="RECIFE"):
    nome_clean = remover_acentos(nome).upper()[:25]
    cidade_clean = remover_acentos(cidade).upper()[:15]
    chave_clean = str(chave).strip()
    str_valor = f"{valor:.2f}"
    
    gui = "0014BR.GOV.BCB.PIX"
    key_part = f"01{len(chave_clean):02d}{chave_clean}"
    merchant_account = f"26{len(gui + key_part):02d}{gui}{key_part}"
    
    cat = "52040000"
    curr = "5303986"
    amount = f"54{len(str_valor):02d}{str_valor}"
    country = "5802BR"
    merchant_name = f"59{len(nome_clean):02d}{nome_clean}"
    merchant_city = f"60{len(cidade_clean):02d}{cidade_clean}"
    add_data = "62070503***"
    
    raw = f"000201{merchant_account}{cat}{curr}{amount}{country}{merchant_name}{merchant_city}{add_data}6304"
    
    crc = 0xFFFF
    for char in raw:
        crc ^= (ord(char) << 8)
        for _ in range(8):
            if (crc & 0x8000) != 0:
                crc = ((crc << 1) ^ 0x1021) & 0xFFFF
            else:
                crc = (crc << 1) & 0xFFFF
    crc_str = f"{crc:04X}"
    return raw + crc_str

# --- LEITURA DAS ABAS DO GOOGLE SHEETS ---
def ler_aba_google_sheets(nome_aba):
    url_csv = f"https://docs.google.com/spreadsheets/d/{SHEET_ID}/gviz/tq?tqx=out:csv&sheet={nome_aba}"
    try:
        df = pd.read_csv(url_csv)
        df.columns = df.columns.str.strip()
        return df
    except Exception:
        url_alt = f"https://docs.google.com/spreadsheets/d/{SHEET_ID}/export?format=csv&sheet={nome_aba}"
        df = pd.read_csv(url_alt)
        df.columns = df.columns.str.strip()
        return df

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

# --- RECIBO PDF ---
def gerar_recibo_pdf(dados):
    pdf = FPDF()
    pdf.add_page()
    pdf.set_line_width(0.5)
    pdf.rect(10, 10, 190, 120)
    
    pdf.set_font("Arial", "B", 16)
    pdf.set_text_color(180, 40, 20)
    pdf.cell(190, 12, "COMPROVANTE DE RESERVA - FEIJOBINGO 2026", ln=True, align="C")
    
    pdf.set_font("Arial", "", 10)
    pdf.set_text_color(0, 0, 0)
    pdf.cell(190, 6, "Paróquia Nossa Senhora do Perpétuo Socorro - Madalena", ln=True, align="C")
    pdf.ln(5)
    
    pdf.set_font("Arial", "B", 11)
    pdf.cell(45, 8, "Comprador(a):", ln=False)
    pdf.set_font("Arial", "", 11)
    pdf.cell(145, 8, str(dados['nome']), ln=True)
    
    pdf.set_font("Arial", "B", 11)
    pdf.cell(45, 8, "WhatsApp / E-mail:", ln=False)
    pdf.set_font("Arial", "", 11)
    pdf.cell(145, 8, f"{dados['whatsapp']} | {dados['email']}", ln=True)
    
    pdf.set_font("Arial", "B", 11)
    pdf.cell(45, 8, "Item Adquirido:", ln=False)
    pdf.set_font("Arial", "B", 11)
    pdf.cell(145, 8, str(dados['item']), ln=True)
    
    pdf.set_font("Arial", "B", 11)
    pdf.cell(45, 8, "Valor Total:", ln=False)
    pdf.set_font("Arial", "", 11)
    pdf.cell(145, 8, f"R$ {dados['valor']:.2f}", ln=True)

    pdf.set_font("Arial", "B", 11)
    pdf.cell(45, 8, "Código do Pedido:", ln=False)
    pdf.set_font("Arial", "", 10)
    pdf.cell(145, 8, str(dados['cod_aut']), ln=True)
    
    pdf.ln(8)
    pdf.set_font("Arial", "I", 9)
    pdf.set_text_color(100, 100, 100)
    pdf.cell(190, 5, "*A validação do acesso e entrega das cartelas será confirmada após a conferência bancária.", ln=True, align="C")
    pdf.cell(190, 5, "Guarde este comprovante temporário com você.", ln=True, align="C")
    return bytes(pdf.output())

# --- SESSION STATE ---
if "pagamento_pendente" not in st.session_state:
    st.session_state.pagamento_pendente = False
if "dados_venda" not in st.session_state:
    st.session_state.dados_venda = {}
if "mesa_selecionada" not in st.session_state:
    st.session_state.mesa_selecionada = None

# --- HEADER COM LOGO ---
st.markdown(
    f"""
    <div style="text-align: center;">
        <img src="{URL_LOGO_IGREJA}" style="max-width: 110px; margin-bottom: 8px;">
    </div>
    """,
    unsafe_allow_html=True
)

st.markdown("<h1 style='text-align: center; margin-top:0; font-size:26px;'>🍲 FeijoBingo 2026 🎟️</h1>", unsafe_allow_html=True)
st.markdown("<p style='text-align: center; font-weight: bold; color: #555; font-size:14px;'>Paróquia da Madalena - Venda Online de Mesas e Cartelas</p>", unsafe_allow_html=True)

modulo = st.sidebar.radio("Navegação:", ["🪑 Reserva de Mesas", "🎯 Cartelas do Bingo Online (4 Prêmios)"])

# ==========================================
# MÓDULO 1: RESERVA DE MESAS
# ==========================================
if modulo == "🪑 Reserva de Mesas":
    if not st.session_state.pagamento_pendente:
        st.subheader("Mapa Físico das Mesas")
        
        URL_MAPA = "https://i.postimg.cc/s2WHBKmr/Mapa-das-Mesas.png"
        st.image(URL_MAPA, caption="Layout Oficial do FeijoBingo: Toque na imagem para ampliar", use_container_width=True)
        
        try:
            df_mesas = ler_aba_google_sheets("Mesas_FeijoBingo")
            df_mesas["ID_Mesa"] = pd.to_numeric(df_mesas["ID_Mesa"], errors='coerce').fillna(0).astype(int)
            
            if "Status" not in df_mesas.columns:
                df_mesas["Status"] = ""
            else:
                df_mesas["Status"] = df_mesas["Status"].fillna("").astype(str).str.strip()
        except Exception as e:
            st.error("Erro ao ler a aba 'Mesas_FeijoBingo'. Verifique se a planilha está aberta para leitura pública.")
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
        
        is_setor_ab = ("Setor A" in setor_escolhido or "Setor B" in setor_escolhido)
        preco_mesa_base = VALOR_MESA_AB if is_setor_ab else VALOR_MESA_CD
        
        mesas_do_setor = intervalos[setor_escolhido]
        
        st.write(f"### Mesas do {setor_escolhido} (Valor: R$ {preco_mesa_base:.2f}):")
        
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
            st.success(f"Mesa Selecionada: **Nº {st.session_state.mesa_selecionada:03d}**")
            
            tipo_compra = "Apenas Mesa"
            preco_final = preco_mesa_base
            
            if is_setor_ab:
                st.info("🔥 **OFERTA ESPECIAL COMBO FEIJOBINGO:**")
                tipo_compra = st.radio(
                    "Escolha a sua modalidade de compra:",
                    [
                        f"🪑 Apenas a Mesa {st.session_state.mesa_selecionada:03d} (R$ {VALOR_MESA_AB:.2f})",
                        f"🎁 COMBO PROMO: Mesa {st.session_state.mesa_selecionada:03d} + 4 Cartelas do Bingo (R$ {VALOR_COMBO:.2f})"
                    ]
                )
                if "COMBO" in tipo_compra:
                    preco_final = VALOR_COMBO
                    descricao_item = f"COMBO PROMO: Mesa Nº {st.session_state.mesa_selecionada:03d} + 4 Cartelas do Bingo"
                else:
                    preco_final = VALOR_MESA_AB
                    descricao_item = f"Mesa Nº {st.session_state.mesa_selecionada:03d} ({setor_escolhido})"
            else:
                descricao_item = f"Mesa Nº {st.session_state.mesa_selecionada:03d} ({setor_escolhido})"

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
                        "valor_total": float(preco_final),
                        "item_descricao": descricao_item
                    }
                    try:
                        res = requests.post(URL_API, json=payload)
                        if "Sucesso" in res.text or res.status_code == 200:
                            st.session_state.dados_venda = {
                                "tipo": "Mesa FeijoBingo",
                                "item": descricao_item,
                                "nome": nome,
                                "whatsapp": whatsapp,
                                "email": email,
                                "valor": preco_final,
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
            
            sub_bingo = st.form_submit_button("Gerar Cartelas e Ir para o Pagamento")
            
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
# PAGAMENTO UNIFICADO
# ==========================================
if st.session_state.pagamento_pendente:
    venda = st.session_state.dados_venda
    st.markdown("---")
    st.subheader("📌 Finalização e Pagamento")
    st.write(f"Comprador: **{venda['nome']}**")
    st.write(f"Item: **{venda['item']}**")
    st.markdown(f"💰 **Valor Total a Pagar: R$ {venda['valor']:.2f}**")
    
    metodo_pagamento = st.radio("Escolha a forma de pagamento:", ["📱 Pix com Valor Exato (Mais Rápido)", "💳 Cartão de Crédito"])
    
    if "Pix" in metodo_pagamento:
        st.markdown("---")
        payload_pix_completo = gerar_payload_pix(CHAVE_PIX_CELULAR, BENEFICIARIO_PIX, venda['valor'])
        
        col_qr, col_txt = st.columns([4, 6])
        with col_qr:
            url_qr = f"https://api.qrserver.com/v1/create-qr-code/?size=220x220&data={requests.utils.quote(payload_pix_completo)}"
            st.image(url_qr, caption="Escaneie no app do banco")
        
        with col_txt:
            st.markdown("#### 📱 Pix Copia e Cola (Valor Automático)")
            st.caption("Copie o código abaixo e cole no seu aplicativo bancário:")
            st.code(payload_pix_completo, language="text")
            
            st.markdown("📱 **Ou Chave Celular Direta:**")
            st.code(CHAVE_PIX_CELULAR, language="text")
            st.write(f"👤 Beneficiário: **{BENEFICIARIO_PIX}**")

    else:
        st.markdown("---")
        st.markdown("#### 💳 Pagamento via Cartão de Crédito")
        st.write("Clique no botão abaixo para ser redirecionado à página de pagamento seguro por cartão de crédito:")
        st.markdown(
            f'<a href="{URL_CARTAO_CREDITO}" target="_blank" style="display:inline-block; background-color:#27ae60; color:white; padding:12px 20px; text-decoration:none; border-radius:8px; font-weight:bold;">👉 Pagar R$ {venda["valor"]:.2f} com Cartão de Crédito</a>',
            unsafe_allow_html=True
        )

    st.markdown("---")
    st.subheader("📄 Baixar Comprovante / Recibo da Reserva")
    
    try:
        pdf_bytes = gerar_recibo_pdf(venda)
        st.download_button(
            label="📥 Baixar Comprovante em PDF",
            data=pdf_bytes,
            file_name=f"Comprovante_FeijoBingo_{venda['nome'].replace(' ', '_')}.pdf",
            mime="application/pdf"
        )
    except Exception as pdf_err:
        st.error(f"Erro ao gerar PDF: {pdf_err}")

    if st.button("Realizar Nova Operação / Voltar"):
        st.session_state.pagamento_pendente = False
        st.session_state.dados_venda = {}
        st.rerun()
