import streamlit as st
import pandas as pd
import requests
import datetime
import unicodedata
import random
import base64
import streamlit.components.v1 as components

try:
    from fpdf import FPDF
except ImportError:
    st.error("Por favor, garanta que 'fpdf2' está listado no arquivo requirements.txt no GitHub.")

# --- 1. CONFIGURAÇÃO DA PÁGINA E ÍCONE DA IGREJA ---
URL_LOGO_IGREJA = "https://i.imgur.com/k3okz8x.png"
URL_CARTELA_OFICIAL = "https://i.postimg.cc/dtbd3x9T/Whats-App-Image-2026-10-31-at-16-26-43.jpg"

st.set_page_config(
    page_title="FeijoBingo 2026 - Paróquia da Madalena", 
    page_icon=URL_LOGO_IGREJA, 
    layout="centered"
)

# INJEÇÃO HTML PARA VIEWPORT COM ZOOM EM CELULARES
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

# CSS RESPONSIVO LIMPO
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

# ENDPOINTS E PARÂMETROS
URL_API = "https://script.google.com/macros/s/AKfycbyAHGNR4OoeKP3tR3xwcSFmx_8eXQcIZfekMn8o_QFPP8jZy9JjdlbT5Xh68OmVUFOD/exec"
SHEET_ID = "1XIhcv1MBsWW7ufFqSPsuj3wxrVoAcD_Dv9zJVq4kvy0"

CHAVE_PIX_CELULAR = "+5581997752112"
BENEFICIARIO_PIX = "PAROQUIA NOSSA SENHORA DO"

# VALORES ATUALIZADOS PASCOM 2026
VALOR_COMBO_MESA = 100.0   # Mesa + 4 Cartelas
VALOR_ENTRADA_IND = 20.0   # Entrada Individual + 1 Cartela
VALOR_CARTELA_AVULSA = 10.0 # Cartela Bingo Avulsa

# REMOÇÃO DE ACENTOS PARA PIX EMV
def remover_acentos(texto):
    return ''.join(
        c for c in unicodedata.normalize('NFD', str(texto))
        if unicodedata.category(c) != 'Mn'
    )

# CÁLCULO DE CRC16 EXATO
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

# GERADOR DE PIX EMV (BR CODE)
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

# LEITURA DE ABAS GOOGLE SHEETS
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

# LEITURA DAS CARTELAS JÁ OCUPADAS/VENDIDAS NA FAIXA DE 101 A 1000
def obter_cartelas_ocupadas():
    try:
        df_b = ler_aba_google_sheets("Cartelas_Bingo")
        if "Comprador_Nome" in df_b.columns and "Num_Cartela" in df_b.columns:
            # Filtra onde já tem comprador preenchido
            df_vendidas = df_b[df_b["Comprador_Nome"].notna() & (df_b["Comprador_Nome"].astype(str).str.strip() != "")]
            nums = df_vendidas["Num_Cartela"].astype(str).str.split(",").explode().str.strip()
            return set(pd.to_numeric(nums, errors='coerce').dropna().astype(int).tolist())
    except Exception:
        pass
    return set()

# GERADOR DE NÚMEROS DE CARTELAS EXCLUSIVAMENTE NA FAIXA DE 101 A 1000
def gerar_numeros_cartelas_aleatorios(qtd, ocupadas):
    disponiveis = [n for n in range(101, 1001) if n not in ocupadas]
    if len(disponiveis) < qtd:
        return disponiveis
    return random.sample(disponiveis, qtd)

# GERADOR DE RECIBO PDF
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

# SESSION STATE
if "pagamento_pendente" not in st.session_state:
    st.session_state.pagamento_pendente = False
if "dados_venda" not in st.session_state:
    st.session_state.dados_venda = {}
if "mesa_selecionada" not in st.session_state:
    st.session_state.mesa_selecionada = None

# HEADER COM LOGO
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

# SIDEBAR: VITRINE DE PRÊMIOS DO BINGO
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
    ["🪑 Combo Mesa + 4 Cartelas (R$ 100)", "🎟️ Entrada Individual + 1 Cartela (R$ 20)", "🎯 Cartela Bingo Avulsa (R$ 10)"]
)

# SEÇÃO EXPANSÍVEL DOS PRÊMIOS NO CORPO DO APP
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
            
            *💡 Vendas de cartelas pelo app restritas do nº 101 ao nº 1000.*
            """
        )

# =========================================================
# MÓDULO 1: COMBO MESA + 4 CARTELAS (R$ 100,00 UNIFICADO)
# =========================================================
if modulo == "🪑 Combo Mesa + 4 Cartelas (R$ 100)":
    if not st.session_state.pagamento_pendente:
        st.subheader("Reserva de Mesa (Inclui 4 Cartelas do Bingo)")
        st.success("🎉 Todas as mesas possuem o valor promocional único de **R$ 100,00** e garantem **4 Cartelas do Bingo**!")
        
        URL_MAPA = "https://i.postimg.cc/s2WHBKmr/Mapa-das-Mesas.png"
        st.image(URL_MAPA, caption="Layout Oficial do FeijoBingo no Clube Português", use_container_width=True)
        
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
        
        mesas_do_setor = intervalos[setor_escolhido]
        st.write(f"### Mesas do {setor_escolhido}:")
        
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
                        if st.session_state.mesa_selecionada == id_m:
                            st.button(f"📌 {id_m:03d}", key=f"m_{id_m}", type="primary", use_container_width=True)
                        else:
                            if st.button(f"{id_m:03d}", key=f"m_{id_m}", type="secondary", use_container_width=True):
                                st.session_state.mesa_selecionada = id_m
                                st.rerun()
                    else:
                        st.button(f"❌ {id_m:03d}", key=f"m_{id_m}", disabled=True, use_container_width=True, help=f"Mesa {status}")

        if st.session_state.mesa_selecionada:
            st.success(f"Mesa Selecionada: **Nº {st.session_state.mesa_selecionada:03d}** (Combo Mesa + 4 Cartelas por R$ 100,00)")
            
            st.markdown("#### 🎯 Escolha das 4 Cartelas do Bingo (Faixa nº 101 ao nº 1000):")
            modo_cartela = st.radio("Como deseja definir os números das suas 4 cartelas?", ["Gerar de Forma Aleatória", "Escolher os Números Manualmente"])
            
            cartelas_ocupadas = obter_cartelas_ocupadas()
            cartelas_definidas = []
            
            if modo_cartela == "Escolher os Números Manualmente":
                c1, c2, c3, c4 = st.columns(4)
                with c1: num1 = st.number_input("Cartela 1:", min_value=101, max_value=1000, value=101, step=1)
                with c2: num2 = st.number_input("Cartela 2:", min_value=101, max_value=1000, value=102, step=1)
                with c3: num3 = st.number_input("Cartela 3:", min_value=101, max_value=1000, value=103, step=1)
                with c4: num4 = st.number_input("Cartela 4:", min_value=101, max_value=1000, value=104, step=1)
                cartelas_definidas = [int(num1), int(num2), int(num3), int(num4)]
            else:
                cartelas_definidas = gerar_numeros_cartelas_aleatorios(4, cartelas_ocupadas)
                st.info(f"Cartelas Geradas: **{', '.join(map(str, cartelas_definidas))}**")

            with st.form("form_mesa"):
                nome = st.text_input("Nome Completo *")
                whatsapp = st.text_input("WhatsApp com DDD *")
                email = st.text_input("E-mail *")
                sub = st.form_submit_button("Avançar para o Pagamento")
                
                if sub and nome and whatsapp and email:
                    if len(set(cartelas_definidas)) < 4:
                        st.error("Não escolha números de cartela repetidos para o mesmo combo.")
                        st.stop()
                    
                    duplicadas = [n for n in cartelas_definidas if n in cartelas_ocupadas]
                    if duplicadas:
                        st.error(f"A(s) cartela(s) {duplicadas} já foi(ram) reservada(s) por outra pessoa. Escolha outro(s) número(s).")
                        st.stop()

                    str_cartelas = ", ".join(map(str, cartelas_definidas))
                    desc_item = f"Combo Mesa Nº {st.session_state.mesa_selecionada:03d} + 4 Cartelas ({str_cartelas})"
                    
                    st.session_state.dados_venda = {
                        "tipo": "Mesa FeijoBingo",
                        "id_mesa": int(st.session_state.mesa_selecionada),
                        "setor": setor_escolhido,
                        "item": desc_item,
                        "nome": nome,
                        "whatsapp": whatsapp,
                        "email": email,
                        "valor": VALOR_COMBO_MESA,
                        "cartelas": str_cartelas,
                        "cod_aut": f"FB26-M{st.session_state.mesa_selecionada:03d}-{int(datetime.datetime.now().timestamp())}"
                    }
                    st.session_state.pagamento_pendente = True
                    st.session_state.mesa_selecionada = None
                    st.rerun()

# =========================================================
# MÓDULO 2: ENTRADA INDIVIDUAL + 1 CARTELA (R$ 20,00)
# =========================================================
elif modulo == "🎟️ Entrada Individual + 1 Cartela (R$ 20)":
    if not st.session_state.pagamento_pendente:
        st.subheader("Entrada Individual (Inclui 1 Cartela do Bingo)")
        st.markdown(f"🎟️ **Valor Unitário:** <span style='color:#27ae60; font-weight:bold;'>R$ {VALOR_ENTRADA_IND:.2f}</span>", unsafe_allow_html=True)
        
        qtd_entradas = st.number_input("Quantidade de Ingressos Individuais:", min_value=1, max_value=20, value=1, step=1)
        valor_total_ind = qtd_entradas * VALOR_ENTRADA_IND
        st.markdown(f"### Total: <span style='color:#27ae60;'>R$ {valor_total_ind:.2f}</span>", unsafe_allow_html=True)
        
        modo_cartela = st.radio(f"Como deseja definir os números da(s) {qtd_entradas} cartela(s)? (Faixa nº 101 ao nº 1000)", ["Gerar de Forma Aleatória", "Escolher os Números Manualmente"])
        cartelas_ocupadas = obter_cartelas_ocupadas()
        cartelas_definidas = []
        
        if modo_cartela == "Escolher os Números Manualmente":
            st.caption("Digite os números desejados para cada cartela (101 a 1000):")
            cols = st.columns(min(int(qtd_entradas), 4))
            for idx in range(int(qtd_entradas)):
                with cols[idx % 4]:
                    val = st.number_input(f"Cartela {idx+1}:", min_value=101, max_value=1000, value=101+idx, key=f"ind_c_{idx}")
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
# MÓDULO 3: CARTELA BINGO AVULSA (R$ 10,00)
# =========================================================
elif modulo == "🎯 Cartela Bingo Avulsa (R$ 10)":
    if not st.session_state.pagamento_pendente:
        st.subheader("Venda de Cartela Bingo Avulsa")
        st.markdown(f"🎟️ **Valor Unitário:** <span style='color:#27ae60; font-weight:bold;'>R$ {VALOR_CARTELA_AVULSA:.2f}</span>", unsafe_allow_html=True)
        st.caption("📌 Vendas via aplicativo disponíveis apenas para o intervalo das cartelas nº 101 ao nº 1000.")
        
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
                    val = st.number_input(f"Cartela {idx+1}:", min_value=101, max_value=1000, value=101+idx, key=f"av_c_{idx}")
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
# PAGAMENTO UNIFICADO + UPLOAD DO COMPROVANTE E GRAVAÇÃO
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
                with st.spinner("Gravando reserva e enviando comprovante..."):
                    bytes_file = comprovante_file.read()
                    b64_file = base64.b64encode(bytes_file).decode('utf-8')
                    
                    data_hoje = datetime.datetime.now().strftime("%d/%m/%Y %H:%M:%S")
                    
                    payload_envio = {
                        "acao": "gravar_reserva_completa",
                        "tipo": venda["tipo"],
                        "id_mesa": str(venda.get("id_mesa", "")),
                        "setor": venda.get("setor", ""),
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
                        # Envio via POST tratando redirecionamento do Apps Script
                        headers = {'Content-Type': 'application/json'}
                        res = requests.post(URL_API, json=payload_envio, headers=headers)
                        
                        if res.status_code == 200 or "Sucesso" in res.text:
                            st.balloons()
                            st.success("🎉 Reserva e Comprovante registrados com sucesso na planilha!")
                            st.info("📧 Um e-mail de notificação foi enviado para a equipe de validação PASCOM.")
                        else:
                            st.error(f"Erro ao salvar: {res.text}")
                    except Exception as err:
                        st.error(f"Erro ao conectar com o Google Apps Script: {err}")

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
        st.rerun()
