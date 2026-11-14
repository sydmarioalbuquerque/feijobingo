import streamlit as st
import pandas as pd
import requests
import datetime
import unicodedata
import random
import base64
import smtplib
from io import BytesIO
from PIL import Image, ImageDraw
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email import encoders
import streamlit.components.v1 as components

try:
    from fpdf import FPDF
except ImportError:
    st.error("Por favor, garanta que 'fpdf2' está listado no seu arquivo requirements.txt no GitHub.")

# --- 1. CONFIGURAÇÃO DA PÁGINA E ÍCONES ---
URL_LOGO_IGREJA = "https://i.imgur.com/k3okz8x.png"
URL_CARTELA_OFICIAL = "https://i.postimg.cc/dtbd3x9T/Whats-App-Image-2026-10-31-at-16-26-43.jpg"
URL_MAPA_LIMPO = "https://i.postimg.cc/s2WHBKmr/Mapa-das-Mesas.png"

st.set_page_config(
    page_title="FeijoBingo 2026 - Paróquia da Madalena", 
    page_icon=URL_LOGO_IGREJA, 
    layout="centered"
)

# INJEÇÃO HTML PARA VIEWPORT E ZOOM EM SMARTPHONES
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

# ESTILIZAÇÃO CSS RESPONSIVA
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

# --- 2. ENDPOINTS E CONFIGURAÇÕES GERAIS ---
URL_API = "https://script.google.com/macros/s/AKfycbyAHGNR4OoeKP3tR3xwcSFmx_8eXQcIZfekMn8o_QFPP8jZy9JjdlbT5Xh68OmVUFOD/exec"
SHEET_ID = "1XIhcv1MBsWW7ufFqSPsuj3wxrVoAcD_Dv9zJVq4kvy0"

CHAVE_PIX_CELULAR = "+5581997752112"
BENEFICIARIO_PIX = "PAROQUIA NOSSA SENHORA DO"

VALOR_COMBO_MESA = 100.0     # Mesa + 4 Cartelas
VALOR_ENTRADA_IND = 25.0    # Entrada Individual + 1 Cartela
VALOR_CARTELA_AVULSA = 10.0 # Cartela Bingo Avulsa

# --- DEFINIÇÃO DAS 248 MESAS LIBERADAS PARA VENDA NO APP ---
SETORES_248_MESAS = {
    "Setor A (Frente Esquerda - 60 Mesas)": list(range(35, 95)),
    "Setor B (Frente Direita - 60 Mesas)": sorted(list(range(95, 148)) + [151, 152, 154, 155, 157, 158, 160]),
    "Setor C (Fundo Esquerdo - 64 Mesas)": [
        m for row_start in range(174, 252, 11) for m in range(row_start, row_start + 8)
    ],
    "Setor D (Fundo Direito - 64 Mesas)": [
        m for row_start in range(277, 348, 10) for m in range(row_start, row_start + 8)
    ]
}

MESAS_PERMITIDAS_SET = set(
    m for lista in SETORES_248_MESAS.values() for m in lista
)

# --- MAPEAMENTO DE COORDENADAS NORMALIZADAS (0.0 a 1.0) DAS 366 MESAS ---
def obter_coordenadas_mapa():
    coords = {}
    
    # 1. Bloco Superior Esquerdo (Mesas 001 a 034 - Laterais / Passarela)
    linhas_esq_top = [
        (0.244, [1, 2]),
        (0.273, [3, 4, 19, 20]),
        (0.304, [5, 6, 21, 22]),
        (0.334, [7, 8, 23, 24]),
        (0.365, [9, 10, 25, 26]),
        (0.397, [11, 12, 27, 28]),
        (0.428, [13, 14, 29, 30]),
        (0.459, [15, 16, 31, 32]),
        (0.491, [17, 18, 33, 34]),
    ]
    xs_esq_top = [0.095, 0.125, 0.181, 0.212]
    for y, ids in linhas_esq_top:
        offset = 2 if len(ids) == 2 else 0
        for idx, m_id in enumerate(ids):
            coords[m_id] = (xs_esq_top[idx + offset], y)

    # 2. Setor A (Mesas 035 a 094)
    linhas_setor_a = [
        (0.304, list(range(35, 43))),
        (0.334, list(range(43, 51))),
        (0.365, list(range(51, 59))),
        (0.397, list(range(59, 68))),
        (0.428, list(range(68, 77))),
        (0.459, list(range(77, 86))),
        (0.491, list(range(86, 95))),
    ]
    for y, ids in linhas_setor_a:
        n = len(ids)
        x_ini = 0.254 if n == 8 else 0.222
        x_fim = 0.471
        for idx, m_id in enumerate(ids):
            x = x_ini + idx * (x_fim - x_ini) / (n - 1)
            coords[m_id] = (x, y)

    # 3. Setor B (Mesas 095 a 171)
    linhas_setor_b = [
        (0.273, [148, 149, 150]),
        (0.304, list(range(95, 102)) + [151, 152, 153]),
        (0.334, list(range(102, 109)) + [154, 155, 156]),
        (0.365, list(range(109, 116)) + [157, 158, 159]),
        (0.397, list(range(116, 124)) + [160, 161, 162]),
        (0.428, list(range(124, 132)) + [163, 164, 165]),
        (0.459, list(range(132, 140)) + [166, 167, 168]),
        (0.491, list(range(140, 148)) + [169, 170, 171]),
    ]
    for y, ids in linhas_setor_b:
        if len(ids) == 3:
            xs = [0.775, 0.806, 0.844]
            for idx, m_id in enumerate(ids):
                coords[m_id] = (xs[idx], y)
        elif len(ids) == 10:
            xs = [0.571, 0.602, 0.633, 0.664, 0.695, 0.726, 0.757, 0.793, 0.824, 0.855]
            for idx, m_id in enumerate(ids):
                coords[m_id] = (xs[idx], y)
        else:
            xs = [0.571, 0.602, 0.633, 0.664, 0.695, 0.726, 0.757, 0.788, 0.822, 0.854, 0.885]
            for idx, m_id in enumerate(ids):
                coords[m_id] = (xs[idx], y)

    # 4. Setor C (Mesas 172 a 270)
    ys_c = [0.580, 0.611, 0.642, 0.673, 0.704, 0.735, 0.766, 0.797, 0.828]
    xs_c = [0.095, 0.125, 0.159, 0.189, 0.222, 0.253, 0.284, 0.315, 0.346, 0.377, 0.408, 0.439, 0.470]
    m_atual = 172
    for r_idx, y in enumerate(ys_c):
        if r_idx < 8:
            for c_idx in range(11):
                coords[m_atual] = (xs_c[c_idx + 2], y)
                m_atual += 1
        else:
            for c_idx in range(11):
                coords[m_atual] = (xs_c[c_idx + 2], y)
                m_atual += 1

    # 5. Setor D (Mesas 277 a 366)
    ys_d = [0.580, 0.611, 0.642, 0.673, 0.704, 0.735, 0.766, 0.797, 0.828]
    xs_d = [0.571, 0.602, 0.633, 0.664, 0.695, 0.726, 0.757, 0.788, 0.822, 0.854]
    m_atual = 277
    for r_idx, y in enumerate(ys_d):
        cols = 10
        for c_idx in range(cols):
            coords[m_atual] = (xs_d[c_idx], y)
            m_atual += 1

    return coords

@st.cache_data(ttl=3600)
def carregar_imagem_base():
    resp = requests.get(URL_MAPA_LIMPO, timeout=10)
    return Image.open(BytesIO(resp.content)).convert("RGBA")

def gerar_mapa_dinamico(df_mesas, mesas_selecionadas):
    img = carregar_imagem_base().copy()
    draw = ImageDraw.Draw(img)
    w, h = img.size
    coords = obter_coordenadas_mapa()
    raio = max(8, int(w * 0.011))

    # Mapeia status atual na planilha
    status_dict = {}
    for _, row in df_mesas.iterrows():
        m_id = int(row["ID_Mesa"])
        status_dict[m_id] = str(row["Status"]).strip().capitalize()

    for m_id, (nx, ny) in coords.items():
        cx, cy = int(nx * w), int(ny * h)
        st_mesa = status_dict.get(m_id, "")
        is_ocupada_planilha = st_mesa not in ("", "Livre", "Nan")
        is_bloqueada_barraca = m_id not in MESAS_PERMITIDAS_SET

        if m_id in mesas_selecionadas:
            # Destaque Azul para mesas selecionadas no momento pelo usuário
            draw.ellipse([cx - raio - 2, cy - raio - 2, cx + raio + 2, cy + raio + 2], outline=(0, 102, 255, 255), width=4)
        elif is_ocupada_planilha or is_bloqueada_barraca:
            # X Vermelho forte para mesas vendidas, reservadas ou destinadas às barracas
            cor_x = (220, 20, 20, 255)
            espessura = max(3, int(w * 0.0035))
            draw.line([cx - raio, cy - raio, cx + raio, cy + raio], fill=cor_x, width=espessura)
            draw.line([cx - raio, cy + raio, cx + raio, cy - raio], fill=cor_x, width=espessura)

    return img

# --- 3. DISPARO DE E-MAIL VIA SMTP ---
def enviar_comprovante_administradores(nome_comprador, item_adquirido, arquivo_upload, cod_aut, valor_pago):
    email_servidor = "sydmario.albuquerque@gmail.com" 
    senha_aplicativo = "mtzk aoud fggp pflm"
    
    emails_destinatarios = ["sydmario.albuquerque@gmail.com", "sydmario@yahoo.com.br", "salajunior@hotmail.com", "talithamey2@gmail.com", "paulapessoa82@gmail.com"]
    
    msg = MIMEMultipart()
    msg['From'] = email_servidor
    msg['To'] = ", ".join(emails_destinatarios)
    msg['Subject'] = f"🔔 Novo Comprovante FeijoBingo 2026 - {nome_comprador}"
    
    corpo_mensagem = f"""
    Atenção Equipe PASCOM / Organização,
    
    Um novo pedido foi registrado pelo aplicativo do FeijoBingo 2026 e aguarda validação:
    
    👤 Nome do Comprador: {nome_comprador}
    🎫 Item Adquirido: {item_adquirido}
    💰 Valor Declarado: R$ {valor_pago:.2f}
    🔑 Código de Autenticação: {cod_aut}
    
    O arquivo do comprovante Pix enviado pelo cliente está anexado a este e-mail.
    Assim que confirmar a entrada do dinheiro na conta paroquial, acesse o Google Sheets ou o Painel de Gestão e mude o status para 'Pago'.
    """
    msg.attach(MIMEText(corpo_mensagem, 'plain'))
    
    try:
        dados_arquivo = arquivo_upload.read()
        part = MIMEBase('application', 'octet-stream')
        part.set_payload(dados_arquivo)
        encoders.encode_base64(part)
        part.add_header('Content-Disposition', f'attachment; filename="{arquivo_upload.name}"')
        msg.attach(part)
        arquivo_upload.seek(0)
        
        server = smtplib.SMTP('smtp.gmail.com', 587)
        server.starttls()
        server.login(email_servidor, senha_aplicativo)
        server.sendmail(email_servidor, emails_destinatarios, msg.as_string())
        server.quit()
        return True
    except Exception as e:
        st.error(f"Erro ao enviar o e-mail para a equipe: {e}")
        return False

# --- 4. FUNÇÕES DE PIX EMV ---
def calcular_crc16(payload):
    crc = 0xFFFF
    for char in payload.encode('utf-8'):
        crc ^= (char << 8)
        for _ in range(8):
            if (crc & 0x8000) != 0:
                crc = ((crc << 1) ^ 0x1021) & 0xFFFF
            else:
                crc = (crc << 1) & 0xFFFF
    return f"{crc:04X}"

def gerar_payload_pix(chave, nome, valor, cidade="RECIFE"):
    str_valor = f"{valor:.2f}"
    merchant_account = "26360014br.gov.bcb.pix0114+5581997752112"
    cat = "52040000"
    curr = "5303986"
    amount = f"54{len(str_valor):02d}{str_valor}"
    country = "5802BR"
    merchant_name = "5925PAROQUIA NOSSA SENHORA DO"
    merchant_city = "6006RECIFE"
    add_data = "62070503***"
    
    raw = f"000201{merchant_account}{cat}{curr}{amount}{country}{merchant_name}{merchant_city}{add_data}6304"
    return raw + calcular_crc16(raw)

# --- 5. LEITURA DE DADOS DO GOOGLE SHEETS ---
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

def obter_cartelas_ocupadas():
    try:
        df_b = ler_aba_google_sheets("Cartelas_Bingo")
        if "Comprador_Nome" in df_b.columns and "Num_Cartela" in df_b.columns:
            df_vendidas = df_b[df_b["Comprador_Nome"].notna() & (df_b["Comprador_Nome"].astype(str).str.strip() != "")]
            nums = df_vendidas["Num_Cartela"].astype(str).str.split(",").explode().str.strip()
            return set(pd.to_numeric(nums, errors='coerce').dropna().astype(int).tolist())
    except Exception:
        pass
    return set()

def gerar_numeros_cartelas_aleatorios(qtd, ocupadas):
    disponiveis = [n for n in range(1, 1201) if n not in ocupadas]
    if len(disponiveis) < qtd:
        return disponiveis
    return random.sample(disponiveis, qtd)

# --- 6. GERADOR DE RECIBO PDF TEMPORÁRIO ---
def gerar_recibo_pdf(dados):
    pdf = FPDF()
    pdf.add_page()
    pdf.set_line_width(0.5)
    pdf.rect(10, 10, 190, 125)
    
    pdf.set_font("Arial", "B", 16)
    pdf.set_text_color(180, 40, 20)
    pdf.cell(190, 12, "COMPROVANTE DE RESERVA - FEIJOBINGO 2026", ln=True, align="C")
    
    pdf.set_font("Arial", "", 10)
    pdf.set_text_color(0, 0, 0)
    pdf.cell(190, 6, "Paróquia Nossa Senhora do Perpétuo Socorro - Madalena", ln=True, align="C")
    pdf.ln(4)
    
    pdf.set_font("Arial", "B", 11)
    pdf.cell(45, 7, "Comprador(a):", ln=False)
    pdf.set_font("Arial", "", 11)
    pdf.cell(145, 7, str(dados['nome']), ln=True)
    
    pdf.set_font("Arial", "B", 11)
    pdf.cell(45, 7, "WhatsApp / E-mail:", ln=False)
    pdf.set_font("Arial", "", 11)
    pdf.cell(145, 7, f"{dados['whatsapp']} | {dados['email']}", ln=True)
    
    pdf.set_font("Arial", "B", 11)
    pdf.cell(45, 7, "Item Adquirido:", ln=False)
    pdf.set_font("Arial", "B", 11)
    pdf.cell(145, 7, str(dados['item']), ln=True)

    if dados.get("cartelas"):
        pdf.set_font("Arial", "B", 11)
        pdf.cell(45, 7, "Cartelas Vinc.:", ln=False)
        pdf.set_font("Arial", "B", 11)
        pdf.set_text_color(39, 174, 96)
        pdf.cell(145, 7, f"Nº {dados['cartelas']}", ln=True)
        pdf.set_text_color(0, 0, 0)
    
    pdf.set_font("Arial", "B", 11)
    pdf.cell(45, 7, "Valor Total:", ln=False)
    pdf.set_font("Arial", "", 11)
    pdf.cell(145, 7, f"R$ {dados['valor']:.2f}", ln=True)

    pdf.set_font("Arial", "B", 11)
    pdf.cell(45, 7, "Código do Pedido:", ln=False)
    pdf.set_font("Arial", "", 10)
    pdf.cell(145, 7, str(dados['cod_aut']), ln=True)
    
    pdf.ln(6)
    pdf.set_font("Arial", "I", 9)
    pdf.set_text_color(100, 100, 100)
    pdf.cell(190, 5, "*A validação do acesso e entrega das cartelas será confirmada após conferência bancária.", ln=True, align="C")
    pdf.cell(190, 5, "Guarde este comprovante temporário com você.", ln=True, align="C")
    return bytes(pdf.output())

# --- 7. CONTROLE DE ESTADO DA SESSÃO ---
if "pagamento_pendente" not in st.session_state:
    st.session_state.pagamento_pendente = False
if "dados_venda" not in st.session_state:
    st.session_state.dados_venda = {}
if "mesas_selecionadas" not in st.session_state:
    st.session_state.mesas_selecionadas = []

# HEADER
st.markdown(
    f"""
    <div style="text-align: center;">
        <img src="{URL_LOGO_IGREJA}" style="max-width: 110px; margin-bottom: 8px;">
    </div>
    """,
    unsafe_allow_html=True
)

st.markdown("<h1 style='text-align: center; margin-top:0; font-size:26px;'>🍲 FeijoBingo 2026 🎟️</h1>", unsafe_allow_html=True)
st.markdown("<p style='text-align: center; font-weight: bold; color: #555; font-size:14px;'>Paróquia da Madalena - Festa de Nossa Senhora do Perpétuo Socorro</p>", unsafe_allow_html=True)
st.markdown("<p style='text-align: center; font-size:13px; color:#777;'>📅 <b>29 de Novembro a partir das 11h</b> | 📍 <b>Clube Português do Recife</b></p>", unsafe_allow_html=True)

# SIDEBAR
st.sidebar.image(URL_CARTELA_OFICIAL, caption="Cartela Oficial do FeijoBingo 2026", use_container_width=True)
st.sidebar.markdown("### 🏆 Prêmios Principais do Bingo:")
st.sidebar.markdown(
    """
    * 📱 **1º Prêmio:** Smartphone
    * 🍟 **2º Prêmio:** Airfryer
    * 🔊 **3º Prêmio:** Caixa de Som Bluetooth
    * 📺 **4º Prêmio:** Smart TV
    * 💰 **5º Prêmio:** R$ 2.000,00 em Dinheiro
    """
)

modulo = st.sidebar.radio(
    "Navegação:", 
    ["🪑 Combo Mesa + 4 Cartelas (R$ 100)", f"🎟️ Entrada Individual + 1 Cartela (R$ {int(VALOR_ENTRADA_IND)})", "🎯 Cartela Bingo Avulsa (R$ 10)"]
)

with st.expander("🎁 Clique aqui para ver a lista dos 5 Prêmios e o Modelo da Cartela Oficial"):
    col_img_premio, col_txt_premio = st.columns([1, 1])
    with col_img_premio:
        st.image(URL_CARTELA_OFICIAL, caption="Cartela Física Oficial 2026", use_container_width=True)
    with col_txt_premio:
        st.markdown("#### 🏆 5 Grandes Prêmios:")
        st.markdown(
            """
            1. 📱 **1º Prêmio:** Smartphone
            2. 🍟 **2º Prêmio:** Airfryer
            3. 🔊 **3º Prêmio:** Caixa de Som Bluetooth
            4. 📺 **4º Prêmio:** Smart TV
            5. 💰 **5º Prêmio:** **R$ 2.000,00** em dinheiro!
            
            *💡 Vendas de cartelas pelo app disponíveis do nº 1 ao nº 1200.*
            """
        )

# =========================================================
# MÓDULO 1: COMBO MESA + 4 CARTELAS (248 MESAS + MAPA DINÂMICO)
# =========================================================
if modulo == "🪑 Combo Mesa + 4 Cartelas (R$ 100)":
    if not st.session_state.pagamento_pendente:
        st.subheader("Reserva de Mesas (Cada Mesa inclui 4 Cartelas do Bingo)")
        st.success("🎉 Cada mesa tem o valor de **R$ 100,00** e garante **4 Cartelas do Bingo**! Você pode selecionar mais de uma mesa.")
        
        try:
            df_mesas = ler_aba_google_sheets("Mesas_FeijoBingo")
            df_mesas["ID_Mesa"] = pd.to_numeric(df_mesas["ID_Mesa"], errors='coerce').fillna(0).astype(int)
            if "Status" not in df_mesas.columns:
                df_mesas["Status"] = ""
            else:
                df_mesas["Status"] = df_mesas["Status"].fillna("").astype(str).str.strip()
        except Exception:
            st.error("Erro ao ler a aba 'Mesas_FeijoBingo'. Verifique a aba no Google Sheets.")
            st.stop()

        # MAPA DINÂMICO COM X VERMELHO NAS INDISPONÍVEIS / VENDIDAS
        try:
            mapa_atualizado = gerar_mapa_dinamico(df_mesas, st.session_state.mesas_selecionadas)
            st.image(mapa_atualizado, caption="Layout Atualizado em Tempo Real (❌ Indisponível/Reservada | 🔵 Selecionada | 🟢 Livre)", use_container_width=True)
        except Exception:
            st.image(URL_MAPA_LIMPO, caption="Layout Oficial do FeijoBingo no Clube Português", use_container_width=True)

        setor_escolhido = st.selectbox(
            "Selecione o Setor no Mapa (248 Mesas Disponíveis para Venda):",
            list(SETORES_248_MESAS.keys())
        )
        
        mesas_do_setor = SETORES_248_MESAS[setor_escolhido]
        st.write(f"### Mesas do {setor_escolhido}:")
        st.caption("Clique no número verde/branco para selecionar ou deselecionar a mesa.")
        
        cols_per_row = 6
        for i in range(0, len(mesas_do_setor), cols_per_row):
            cols = st.columns(cols_per_row)
            chunk = mesas_do_setor[i:i + cols_per_row]
            for idx, id_m in enumerate(chunk):
                dados_m = df_mesas[df_mesas["ID_Mesa"] == id_m]
                status = str(dados_m.iloc[0]["Status"]).strip().capitalize() if not dados_m.empty else ""
                is_livre = (status == "" or status == "Livre" or status == "Nan")
                
                with cols[idx]:
                    if is_livre:
                        if id_m in st.session_state.mesas_selecionadas:
                            if st.button(f"📌 {id_m:03d}", key=f"m_{id_m}", type="primary", use_container_width=True):
                                st.session_state.mesas_selecionadas.remove(id_m)
                                st.rerun()
                        else:
                            if st.button(f"{id_m:03d}", key=f"m_{id_m}", type="secondary", use_container_width=True):
                                st.session_state.mesas_selecionadas.append(id_m)
                                st.rerun()
                    else:
                        st.button(f"❌ {id_m:03d}", key=f"m_{id_m}", disabled=True, use_container_width=True, help=f"Mesa {status}")

        if st.session_state.mesas_selecionadas:
            st.session_state.mesas_selecionadas.sort()
            qtd_mesas = len(st.session_state.mesas_selecionadas)
            str_mesas_sel = ", ".join([f"Nº {m:03d}" for m in st.session_state.mesas_selecionadas])
            total_combo_mesas = qtd_mesas * VALOR_COMBO_MESA
            qtd_total_cartelas = qtd_mesas * 4

            st.success(f"Mesas Selecionadas ({qtd_mesas}): **{str_mesas_sel}** | Total: **R$ {total_combo_mesas:.2f}** ({qtd_total_cartelas} Cartelas)")
            
            if st.button("🗑️ Limpar Seleção de Mesas"):
                st.session_state.mesas_selecionadas = []
                st.rerun()

            st.markdown(f"#### 🎯 Escolha das {qtd_total_cartelas} Cartelas do Bingo (Faixa nº 1 ao nº 1200):")
            modo_cartela = st.radio("Como deseja definir os números das suas cartelas?", ["Gerar de Forma Aleatória", "Escolher os Números Manualmente"])
            
            cartelas_ocupadas = obter_cartelas_ocupadas()
            cartelas_definidas = []
            
            if modo_cartela == "Escolher os Números Manualmente":
                cols_c = st.columns(min(qtd_total_cartelas, 4))
                for idx in range(qtd_total_cartelas):
                    with cols_c[idx % 4]:
                        val_num = st.number_input(f"Cartela {idx+1}:", min_value=1, max_value=1200, value=1+idx, step=1, key=f"mesa_c_{idx}")
                        cartelas_definidas.append(int(val_num))
            else:
                cartelas_definidas = gerar_numeros_cartelas_aleatorios(qtd_total_cartelas, cartelas_ocupadas)
                st.info(f"Cartelas Geradas: **{', '.join(map(str, cartelas_definidas))}**")

            with st.form("form_mesa"):
                nome = st.text_input("Nome Completo *")
                whatsapp = st.text_input("WhatsApp com DDD *")
                email = st.text_input("E-mail *")
                sub = st.form_submit_button("Avançar para o Pagamento")
                
                if sub and nome and whatsapp and email:
                    if len(set(cartelas_definidas)) < qtd_total_cartelas:
                        st.error("Não escolha números de cartela repetidos para os combos.")
                        st.stop()
                    
                    duplicadas = [n for n in cartelas_definidas if n in cartelas_ocupadas]
                    if duplicadas:
                        st.error(f"A(s) cartela(s) {duplicadas} já foi(ram) reservada(s). Escolha outro(s) número(s).")
                        st.stop()

                    str_cartelas = ", ".join(map(str, cartelas_definidas))
                    str_ids_mesas = ", ".join([str(m) for m in st.session_state.mesas_selecionadas])
                    desc_item = f"{qtd_mesas}x Combo Mesa(s) ({str_mesas_sel}) + {qtd_total_cartelas} Cartelas ({str_cartelas})"
                    
                    st.session_state.dados_venda = {
                        "tipo": "Mesa FeijoBingo",
                        "id_mesa": str_ids_mesas,
                        "setor": setor_escolhido,
                        "item": desc_item,
                        "nome": nome,
                        "whatsapp": whatsapp,
                        "email": email,
                        "valor": total_combo_mesas,
                        "cartelas": str_cartelas,
                        "cod_aut": f"FB26-M{st.session_state.mesas_selecionadas[0]:03d}-{int(datetime.datetime.now().timestamp())}"
                    }
                    st.session_state.pagamento_pendente = True
                    st.session_state.mesas_selecionadas = []
                    st.rerun()

# =========================================================
# MÓDULO 2: ENTRADA INDIVIDUAL + 1 CARTELA (R$ 25,00)
# =========================================================
elif modulo == f"🎟️ Entrada Individual + 1 Cartela (R$ {int(VALOR_ENTRADA_IND)})":
    if not st.session_state.pagamento_pendente:
        st.subheader("Entrada Individual (Inclui 1 Cartela do Bingo)")
        st.markdown(f"🎟️ **Valor Unitário:** <span style='color:#27ae60; font-weight:bold;'>R$ {VALOR_ENTRADA_IND:.2f}</span>", unsafe_allow_html=True)
        
        qtd_entradas = st.number_input("Quantidade de Ingressos Individuais:", min_value=1, max_value=20, value=1, step=1)
        valor_total_ind = qtd_entradas * VALOR_ENTRADA_IND
        st.markdown(f"### Total: <span style='color:#27ae60;'>R$ {valor_total_ind:.2f}</span>", unsafe_allow_html=True)
        
        modo_cartela = st.radio(f"Como deseja definir os números da(s) {qtd_entradas} cartela(s)? (Faixa nº 1 ao nº 1200)", ["Gerar de Forma Aleatória", "Escolher os Números Manualmente"])
        cartelas_ocupadas = obter_cartelas_ocupadas()
        cartelas_definidas = []
        
        if modo_cartela == "Escolher os Números Manualmente":
            st.caption("Digite os números desejados para cada cartela (1 a 1200):")
            cols = st.columns(min(int(qtd_entradas), 4))
            for idx in range(int(qtd_entradas)):
                with cols[idx % 4]:
                    val = st.number_input(f"Cartela {idx+1}:", min_value=1, max_value=1200, value=1+idx, key=f"ind_c_{idx}")
                    cartelas_definidas.append(int(val))
        else:
            cartelas_definidas = gerar_numeros_cartelas_aleatorios(int(qtd_entradas), cartelas_ocupadas)
            st.info(f"Cartela(s) Gerada(s): **{', '.join(map(str, cartelas_definidas))}**")

        with st.form("form_entrada_ind"):
            nome = st.text_input("Nome Completo do Titular *")
            whatsapp = st.text_input("WhatsApp com DDD *")
            email = st.text_input("E-mail *")
            sub_ind = st.form_submit_button("Avançar para o Pagamento")
            
            if sub_ind and nome and whatsapp and email:
                if len(set(cartelas_definidas)) < int(qtd_entradas):
                    st.error("Não insira números de cartela repetidos.")
                    st.stop()
                    
                duplicadas = [n for n in cartelas_definidas if n in cartelas_ocupadas]
                if duplicadas:
                    st.error(f"A(s) cartela(s) {duplicadas} já foi(ram) reservada(s). Escolha outro(s) número(s).")
                    st.stop()

                str_cartelas = ", ".join(map(str, cartelas_definidas))
                desc_item = f"{qtd_entradas}x Entrada Individual + Cartela(s) ({str_cartelas})"
                
                st.session_state.dados_venda = {
                    "tipo": "Entrada Individual",
                    "qtd": int(qtd_entradas),
                    "item": desc_item,
                    "nome": nome,
                    "whatsapp": whatsapp,
                    "email": email,
                    "valor": valor_total_ind,
                    "cartelas": str_cartelas,
                    "cod_aut": f"FB26-IND-{int(datetime.datetime.now().timestamp())}"
                }
                st.session_state.pagamento_pendente = True
                st.rerun()

# =========================================================
# MÓDULO 3: CARTELA BINGO AVULSA
# =========================================================
elif modulo == "🎯 Cartela Bingo Avulsa (R$ 10)":
    if not st.session_state.pagamento_pendente:
        st.subheader("Venda de Cartela Bingo Avulsa")
        st.markdown(f"🎟️ **Valor Unitário:** <span style='color:#27ae60; font-weight:bold;'>R$ {VALOR_CARTELA_AVULSA:.2f}</span>", unsafe_allow_html=True)
        st.caption("📌 Vendas via aplicativo disponíveis para o intervalo das cartelas nº 1 ao nº 1200.")
        
        qtd_cartelas = st.number_input("Quantidade de Cartelas Avulsas:", min_value=1, max_value=50, value=1, step=1)
        valor_total_bingo = qtd_cartelas * VALOR_CARTELA_AVULSA
        st.markdown(f"### Total: <span style='color:#27ae60;'>R$ {valor_total_bingo:.2f}</span>", unsafe_allow_html=True)
        
        modo_cartela = st.radio(f"Como deseja definir a(s) {qtd_cartelas} cartela(s)?", ["Gerar de Forma Aleatória", "Escolher os Números Manualmente"])
        cartelas_ocupadas = obter_cartelas_ocupadas()
        cartelas_definidas = []
        
        if modo_cartela == "Escolher os Números Manualmente":
            cols = st.columns(min(int(qtd_cartelas), 4))
            for idx in range(int(qtd_cartelas)):
                with cols[idx % 4]:
                    val = st.number_input(f"Cartela {idx+1}:", min_value=1, max_value=1200, value=1+idx, key=f"av_c_{idx}")
                    cartelas_definidas.append(int(val))
        else:
            cartelas_definidas = gerar_numeros_cartelas_aleatorios(int(qtd_cartelas), cartelas_ocupadas)
            st.info(f"Cartela(s) Gerada(s): **{', '.join(map(str, cartelas_definidas))}**")

        with st.form("form_bingo"):
            nome = st.text_input("Nome Completo do Titular *")
            whatsapp = st.text_input("WhatsApp (para contato de prêmios) *")
            email = st.text_input("E-mail *")
            sub_bingo = st.form_submit_button("Gerar Cartelas e Ir para o Pagamento")
            
            if sub_bingo and nome and whatsapp and email:
                if len(set(cartelas_definidas)) < int(qtd_cartelas):
                    st.error("Não insira números repetidos.")
                    st.stop()
                    
                duplicadas = [n for n in cartelas_definidas if n in cartelas_ocupadas]
                if duplicadas:
                    st.error(f"A(s) cartela(s) {duplicadas} já foi(ram) reservada(s). Escolha outro(s) número(s).")
                    st.stop()

                str_cartelas = ", ".join(map(str, cartelas_definidas))
                desc_item = f"{qtd_cartelas}x Cartela(s) Bingo Avulsa ({str_cartelas})"
                
                st.session_state.dados_venda = {
                    "tipo": "Bingo Online",
                    "qtd_cartelas": int(qtd_cartelas),
                    "item": desc_item,
                    "nome": nome,
                    "whatsapp": whatsapp,
                    "email": email,
                    "valor": valor_total_bingo,
                    "cartelas": str_cartelas,
                    "cod_aut": f"FB26-BG-{int(datetime.datetime.now().timestamp())}"
                }
                st.session_state.pagamento_pendente = True
                st.rerun()

# =========================================================
# FINALIZAÇÃO, PAGAMENTO E ENVIO DE COMPROVANTE
# =========================================================
if st.session_state.pagamento_pendente:
    venda = st.session_state.dados_venda
    st.markdown("---")
    st.subheader("📌 Finalização, Pagamento e Comprovante")
    st.write(f"Comprador: **{venda['nome']}**")
    st.write(f"Item Adquirido: **{venda['item']}**")
    if venda.get("cartelas"):
        st.markdown(f"🎟️ **Número(s) da(s) Cartela(s): <span style='color:#27ae60;'>{venda['cartelas']}</span>**", unsafe_allow_html=True)
    st.markdown(f"💰 **Valor Total a Pagar: R$ {venda['valor']:.2f}**")
    
    metodo_pagamento = st.radio("Escolha a forma de pagamento:", ["📱 Pix com Valor Exato (Mais Rápido)", "💳 Cartão de Crédito (Presencial)"])
    
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

        st.markdown("---")
        st.markdown("### 📤 Envio do Comprovante de Pagamento Pix")
        st.info("Após efetuar o Pix no app do seu banco, anexe o comprovante abaixo para confirmar e garantir a sua reserva na planilha.")
        
        comprovante_file = st.file_uploader("Anexe aqui o Comprovante Pix (JPG, PNG ou PDF):", type=["png", "jpg", "jpeg", "pdf"])
        
        if st.button("✅ Confirmar Reserva e Enviar Comprovante", type="primary"):
            if comprovante_file is None:
                st.warning("Por favor, selecione e anexe o arquivo do comprovante antes de confirmar.")
            else:
                with st.spinner("Gravando reserva e enviando comprovante por e-mail..."):
                    envio_email_sucesso = enviar_comprovante_administradores(
                        venda["nome"], 
                        venda["item"], 
                        comprovante_file, 
                        venda["cod_aut"],
                        float(venda["valor"])
                    )
                    
                    bytes_file = comprovante_file.read()
                    b64_file = base64.b64encode(bytes_file).decode('utf-8')
                    comprovante_file.seek(0)
                    
                    data_hoje = datetime.datetime.now().strftime("%d/%m/%Y %H:%M:%S")
                    payload_envio = {
                        "ID_Mesa": str(venda.get("id_mesa", "")),
                        "Setor": venda.get("setor", ""),
                        "Comprador_Nome": venda["nome"],
                        "Comprador_WhatsApp": venda["whatsapp"],
                        "Comprador_Email": venda["email"],
                        "Data_Venda": data_hoje,
                        "Valor_Pago": float(venda["valor"]),
                        "Num_Cartela": str(venda.get("cartelas", "")),
                        "Status": "Reservada",
                        "Comprovante_Nome": comprovante_file.name,
                        "Comprovante_Base64": b64_file
                    }    
                    
                    try:
                        headers = {'Content-Type': 'application/json'}
                        res = requests.post(URL_API, json=payload_envio, headers=headers)
                        
                        if res.status_code == 200 or "Sucesso" in res.text:
                            st.balloons()
                            st.success("🎉 Reserva e Comprovante registrados com sucesso na planilha!")
                            if envio_email_sucesso:
                                st.info("📧 O comprovante foi enviado com sucesso para o e-mail da equipe PASCOM!")
                        else:
                            st.error(f"Erro ao gravar na planilha: {res.text}")
                    except Exception as err:
                        st.error(f"Erro de conexão com o servidor Google Script: {err}")

    else:
        st.markdown("---")
        st.markdown("#### 💳 Pagamento via Cartão de Crédito")
        st.warning("⚠️ **Aviso:** As compras via Cartão de Crédito estão sendo realizadas **exclusivamente de forma presencial** na Secretaria da Paróquia ou ao final das Missas.")

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
        st.session_state.mesas_selecionadas = []
        st.rerun()
