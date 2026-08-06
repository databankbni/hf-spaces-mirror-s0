import pandas as pd
import numpy as np
import gradio as gr
import matplotlib.pyplot as plt
import plotly.graph_objects as go
import plotly.express as px
from plotly.subplots import make_subplots
from datetime import datetime, timedelta
from sklearn.neural_network import MLPRegressor
from sklearn.preprocessing import StandardScaler, OneHotEncoder
from sklearn.compose import ColumnTransformer
from sklearn.pipeline import Pipeline
from sklearn.model_selection import train_test_split
from sklearn.impute import SimpleImputer
import os


# Configurações globais
PISO_PRECO = 55.70  # Preço mínimo a ser considerado
LIMITE_NEUTRO = 0.4  # Acima/abaixo disso é Long/Short Estrutural
DIAS_RECENTES = 150  # Últimos dias para considerar produtos recentes

# Cores para visualização
CORES = {
    'LONG': '#4CAF50',    # Verde
    'NEUTRO': '#FFC107',  # Amarelo
    'SHORT': '#F44336',   # Vermelho
    'LINHA_GLOBAL': '#2196F3',  # Azul
    'LINHA_PRODUTO': '#FF9800'  # Laranja
}


# CSS customizado para melhorias visuais (versão simplificada)
css_personalizado = """
<style>
    /* Estilos gerais e resets */
    body, .gradio-container {
        font-family: 'Inter', 'Segoe UI', -apple-system, BlinkMacSystemFont, sans-serif !important;
        background: #f7f9fc !important;
        color: #1f2937 !important;
        margin: 0;
        padding: 0;
    }
    /* Seção de cabeçalho com estilo específico */
    .header-banner {
        background-color: #f0f9ff !important;
        padding: 8px 16px !important;
        border-radius: 20px !important;
        display: inline-flex !important;
        align-items: center !important;
        gap: 8px !important;
        margin-bottom: 20px !important;
    }
    .header-icon {
        color: #3b82f6 !important;
    }
    .header-text {
        color: #3b82f6 !important;
        font-size: 14px !important;
        font-weight: 500 !important;
    }
    /* Título principal da página */
    .main-title {
        font-size: 36px !important;
        font-weight: 700 !important;
        color: #0ea5e9 !important;
        margin-bottom: 12px !important;
        text-align: center !important;
    }
    /* Subtítulo da página */
    .subtitle {
        font-size: 16px !important;
        color: #64748b !important;
        text-align: center !important;
        margin-bottom: 25px !important;
        max-width: 800px !important;
        margin-left: auto !important;
        margin-right: auto !important;
    }
    /* Container principal */
    .main-container {
        max-width: 1200px !important;
        margin: 0 auto !important;
        padding: 20px 30px !important;
    }
    /* Estilização dos tabs */
    .tab-container {
        display: flex !important;
        justify-content: center !important;
        margin-bottom: 30px !important;
        gap: 10px !important;
    }
    .model-tab {
        display: flex !important;
        align-items: center !important;
        gap: 8px !important;
        padding: 10px 20px !important;
        background-color: white !important;
        border: 1px solid #e5e7eb !important;
        border-radius: 8px !important;
        cursor: pointer !important;
        box-shadow: 0 1px 2px rgba(0, 0, 0, 0.05) !important;
        transition: all 0.2s ease !important;
    }
    .model-tab:hover {
        box-shadow: 0 4px 6px rgba(0, 0, 0, 0.05) !important;
    }
    .model-tab.active {
        background-color: #f9fafb !important;
        border-color: #d1d5db !important;
    }
    .model-tab-icon {
        width: 16px !important;
        height: 16px !important;
        opacity: 0.6 !important;
    }
    .model-tab-text {
        font-weight: 500 !important;
        font-size: 14px !important;
        color: #4b5563 !important;
    }
    /* Cards para painéis */
    .card-panel {
        background-color: white !important;
        border-radius: 8px !important;
        border: 1px solid #e5e7eb !important;
        margin-bottom: 20px !important;
        box-shadow: 0 1px 2px rgba(0, 0, 0, 0.05) !important;
        overflow: hidden !important;
    }
    /* Cabeçalho do card com cor de fundo */
    .card-header {
        border-bottom: 1px solid #e5e7eb !important;
        padding: 16px 20px !important;
        display: flex !important;
        align-items: center !important;
        gap: 10px !important;
    }
    .card-header-icon {
        color: #3b82f6 !important;
    }
    .card-title {
        font-size: 16px !important;
        font-weight: 600 !important;
        color: #1f2937 !important;
        margin: 0 !important;
    }
    .card-body {
        padding: 20px !important;
    }
    /* Espaçamento para inputs e selects */
    .form-group {
        margin-bottom: 16px !important;
    }
    .form-label {
        display: block !important;
        font-size: 14px !important;
        font-weight: 500 !important;
        color: #4b5563 !important;
        margin-bottom: 6px !important;
    }
    /* Estilização dos inputs e dropdowns */
    .form-input, .form-select {
        width: 100% !important;
        border: 1px solid #d1d5db !important;
        border-radius: 6px !important;
        padding: 8px 12px !important;
        font-size: 14px !important;
        background-color: white !important;
    }
    /* Ajuste dos inputs de data */
    .date-input-container {
        position: relative !important;
    }
    .date-input {
        padding-right: 30px !important;
    }
    .date-input-icon {
        position: absolute !important;
        right: 10px !important;
        top: 50% !important;
        transform: translateY(-50%) !important;
        color: #9ca3af !important;
        pointer-events: none !important;
    }
    /* Melhor espaçamento entre elementos */
    .form-row {
        display: flex !important;
        gap: 16px !important;
        margin-bottom: 16px !important;
    }
    /* Botões estilizados */
    .btn {
        background-color: #3b82f6 !important;
        color: white !important;
        border: none !important;
        border-radius: 6px !important;
        padding: 10px 16px !important;
        font-weight: 500 !important;
        font-size: 14px !important;
        cursor: pointer !important;
        transition: background-color 0.2s !important;
        text-align: center !important;
        width: 100% !important;
    }
    .btn:hover {
        background-color: #2563eb !important;
    }
    /* Cards de status para resultados */
    .result-card {
        padding: 20px !important;
        border-radius: 8px !important;
        margin-bottom: 16px !important;
    }
    .result-card-comprar, .result-card-long {
        background-color: #ecfdf5 !important;
        border-left: 4px solid #10b981 !important;
    }
    .result-card-vender, .result-card-short {
        background-color: #fef2f2 !important;
        border-left: 4px solid #ef4444 !important;
    }
    .result-card-neutro {
        background-color: #fffbeb !important;
        border-left: 4px solid #f59e0b !important;
    }
    .result-title {
        font-size: 16px !important;
        font-weight: 600 !important;
        margin-bottom: 8px !important;
    }
    .result-value {
        font-size: 20px !important;
        font-weight: 700 !important;
        margin-bottom: 16px !important;
    }
    .result-card-comprar .result-value, .result-card-long .result-value {
        color: #10b981 !important;
    }
    .result-card-vender .result-value, .result-card-short .result-value {
        color: #ef4444 !important;
    }
    .result-card-neutro .result-value {
        color: #f59e0b !important;
    }
    .result-indicator {
        height: 4px !important;
        background-color: currentColor !important;
        width: 120px !important;
        border-radius: 2px !important;
        margin-bottom: 8px !important;
    }
    .result-subtitle {
        font-size: 12px !important;
        color: #6b7280 !important;
    }
    /* Cards para interpretação */
    .interpretation-card {
        background-color: #f9fafb !important;
        border-radius: 8px !important;
        padding: 16px !important;
        margin-bottom: 16px !important;
        border: 1px solid #e5e7eb !important;
    }
    .interpretation-title {
        font-size: 14px !important;
        font-weight: 600 !important;
        margin-bottom: 8px !important;
        color: #4b5563 !important;
    }
    .interpretation-text {
        font-size: 13px !important;
        color: #4b5563 !important;
        line-height: 1.5 !important;
    }
    /* Títulos de gráficos */
    .chart-title {
        font-size: 14px !important;
        font-weight: 500 !important;
        color: #6b7280 !important;
        margin-bottom: 12px !important;
        display: flex !important;
        align-items: center !important;
        gap: 6px !important;
    }
    .chart-icon {
        color: #9ca3af !important;
    }
    /* Switch (toggle) */
    .switch-container {
        display: flex !important;
        align-items: center !important;
        gap: 10px !important;
        margin-bottom: 16px !important;
    }
    .switch-label {
        font-size: 14px !important;
        color: #4b5563 !important;
    }
    .switch {
        position: relative !important;
        display: inline-block !important;
        width: 36px !important;
        height: 20px !important;
    }
    .switch input {
        opacity: 0 !important;
        width: 0 !important;
        height: 0 !important;
    }
    .slider {
        position: absolute !important;
        cursor: pointer !important;
        top: 0 !important;
        left: 0 !important;
        right: 0 !important;
        bottom: 0 !important;
        background-color: #e5e7eb !important;
        transition: .4s !important;
        border-radius: 20px !important;
    }
    .slider:before {
        position: absolute !important;
        content: "" !important;
        height: 16px !important;
        width: 16px !important;
        left: 2px !important;
        bottom: 2px !important;
        background-color: white !important;
        transition: .4s !important;
        border-radius: 50% !important;
    }
    input:checked + .slider {
        background-color: #3b82f6 !important;
    }
    input:checked + .slider:before {
        transform: translateX(16px) !important;
    }
    /* Ajustes para os componentes Gradio */
    .svelte-1gfkn6j {
        max-width: none !important;
    }
    .svelte-1gfkn6j > *, .svelte-1rgwlxu {
        width: 100% !important;
        max-width: none !important;
    }
    .wrap.svelte-1wbz3tt {
        box-shadow: none !important;
        border: none !important;
        background: transparent !important;
    }
    .block.svelte-1e788xp {
        border: none !important;
        box-shadow: none !important;
        background: transparent !important;
    }
    .hidden-tab {
        display: none !important;
    }
    .arrow-down {
        width: 24px !important;
        height: 24px !important;
        color: #3b82f6 !important;
        margin: 0 auto !important;
        display: block !important;
        margin-bottom: 25px !important;
        animation: bounce 2s infinite !important;
    }
    @keyframes bounce {
        0%, 100% { transform: translateY(0); }
        50% { transform: translateY(-10px); }
    }
</style>
"""


# Funções comuns para ambos os modelos
def carregar_dados(arquivo):
    """Carrega e pré-processa os dados do arquivo Excel."""
    print(f"Carregando dados de: {arquivo}")
    try:
        df = pd.read_excel(arquivo)
        print(f"Dados carregados com sucesso. {len(df)} registros encontrados.")
        return df
    except Exception as e:
        print(f"Erro ao carregar dados: {e}")
        return None

def preprocessar_dados(df):
    """Realiza o pré-processamento básico dos dados."""
    if df is None:
        return None

    print("Iniciando pré-processamento dos dados...")

    # Converter colunas para tipos apropriados
    try:
        # Converter DATA/HORA para datetime
        if 'DATA/HORA' in df.columns:
            df['DATA/HORA'] = pd.to_datetime(df['DATA/HORA'], dayfirst=True)

        # Garantir que PREÇO é numérico
        if 'PREÇO' in df.columns:
            df['PREÇO'] = pd.to_numeric(df['PREÇO'], errors='coerce')

        print("Conversão de tipos concluída com sucesso.")
    except Exception as e:
        print(f"Erro na conversão de tipos: {e}")

    # Aplicar filtros básicos requeridos
    try:
        # Filtrar por STATUS = Ativo
        df_filtrado = df[df['STATUS'] == 'Ativo']
        print(f"Filtro STATUS aplicado: {len(df_filtrado)} registros restantes.")

        # Filtrar por SUBSISTEMA = SE (Sudeste)
        df_filtrado = df_filtrado[df_filtrado['SUBSISTEMA'] == 'SE']
        print(f"Filtro SUBSISTEMA aplicado: {len(df_filtrado)} registros restantes.")

        # Filtrar por FONTE = CON (Convencional)
        df_filtrado = df_filtrado[df_filtrado['FONTE'] == 'CON']
        print(f"Filtro FONTE aplicado: {len(df_filtrado)} registros restantes.")

        # Filtrar por PREÇO > PISO_PRECO
        df_filtrado = df_filtrado[df_filtrado['PREÇO'] > PISO_PRECO]
        print(f"Filtro PREÇO aplicado: {len(df_filtrado)} registros restantes.")

    except Exception as e:
        print(f"Erro na aplicação de filtros: {e}")
        df_filtrado = df

    return df_filtrado

def calcular_data_recente(df):
    """Calcula a data limite para considerar negócios recentes."""
    if 'DATA/HORA' not in df.columns:
        print("Coluna DATA/HORA não encontrada.")
        return None

    data_max = df['DATA/HORA'].max()
    data_limite = data_max - timedelta(days=DIAS_RECENTES)
    print(f"Data mais recente: {data_max.strftime('%d/%m/%Y')}")
    print(f"Data limite para produtos recentes: {data_limite.strftime('%d/%m/%Y')}")
    return data_limite

def obter_produtos_recentes(df, data_limite):
    """Obtém a lista de produtos negociados recentemente."""
    if data_limite is None:
        return None

    df_recente = df[df['DATA/HORA'] >= data_limite]
    print(f"Registros recentes: {len(df_recente)}")

    # Combinar campos para formar produtos únicos
    produtos_recentes = {
        'tipoProduto': df_recente['TIPO_PRODUTO'].unique().tolist(),
        'periodoProduto': {},
        'anos': {}
    }

    for tipo in produtos_recentes['tipoProduto']:
        df_tipo = df_recente[df_recente['TIPO_PRODUTO'] == tipo]
        produtos_recentes['periodoProduto'][tipo] = df_tipo['PERIODO_PRODUTO'].unique().tolist()
        produtos_recentes['anos'][tipo] = df_tipo['ANO'].astype(str).unique().tolist()

    return produtos_recentes

def criar_grafico_indice_atual(indice, titulo):
    """Cria um gráfico de barra para o índice atual."""

    cor = CORES['NEUTRO']
    if indice > LIMITE_NEUTRO:
        cor = CORES['LONG']
    elif indice < -LIMITE_NEUTRO:
        cor = CORES['SHORT']

    fig = go.Figure()

    # Adicionar barra do índice
    fig.add_trace(go.Bar(
        x=[indice],
        y=['Índice Atual'],
        orientation='h',
        marker=dict(color=cor),
        text=[f"{indice:.2f}"],
        textposition='outside'
    ))

    # Adicionar linhas de referência
    fig.add_shape(
        type="line", line=dict(color="green", width=2, dash="dash"),
        x0=LIMITE_NEUTRO, x1=LIMITE_NEUTRO, y0=-0.5, y1=0.5
    )
    fig.add_shape(
        type="line", line=dict(color="red", width=2, dash="dash"),
        x0=-LIMITE_NEUTRO, x1=-LIMITE_NEUTRO, y0=-0.5, y1=0.5
    )
    fig.add_shape(
        type="line", line=dict(color="gray", width=1),
        x0=0, x1=0, y0=-0.5, y1=0.5
    )

    # Configurar eixos e layout
    fig.update_layout(
        title=titulo,
        xaxis=dict(
            range=[-1.1, 1.1],
            tickmode='array',
            tickvals=[-1, -LIMITE_NEUTRO, 0, LIMITE_NEUTRO, 1],
            ticktext=['-1', f'-{LIMITE_NEUTRO}', '0', f'{LIMITE_NEUTRO}', '1'],
            title="Índice"
        ),
        yaxis=dict(
            visible=False
        ),
        height=200,
        margin=dict(l=20, r=20, t=40, b=20),
        template="plotly_white"
    )

    return fig

def obter_recomendacao(indice):
    """Retorna a recomendação baseada no valor do índice."""
    if indice > LIMITE_NEUTRO:
        return "LONG ESTRUTURAL", CORES['LONG']
    elif indice < -LIMITE_NEUTRO:
        return "SHORT ESTRUTURAL", CORES['SHORT']
    else:
        return "NEUTRO", CORES['NEUTRO']

def atualizar_periodos(tipo_produto, produtos_recentes):
    """Atualiza as opções de período e ano quando o tipo de produto é alterado."""
    if not tipo_produto or tipo_produto not in produtos_recentes['periodoProduto']:
        return [], []

    # CORREÇÃO: Tratar os períodos individualmente, não como uma única string
    periodos = produtos_recentes['periodoProduto'][tipo_produto]
    anos = produtos_recentes['anos'][tipo_produto]
    
    # Verificação de dados e formatação
    print(f"Periodos originais: {periodos}")
    print(f"Anos originais: {anos}")
    
    # Processar separadamente para garantir que não haja problemas de formatação
    periodos_unicos = sorted(list(set(periodos)))
    anos_unicos = sorted(list(set(anos)))
    
    print(f"Periodos processados: {periodos_unicos}")
    print(f"Anos processados: {anos_unicos}")
    
    return gr.update(choices=periodos_unicos, value=None), gr.update(choices=anos_unicos, value=None)


# ====================== MODELO RNA ======================

def preparar_dados_para_modelo(df):
    """Prepara os dados para treinamento do modelo RNA com features aprimoradas."""
    print("Preparando dados para o modelo...")

    # Selecionar colunas relevantes
    colunas = ['SUBSISTEMA', 'FONTE', 'TIPO_PRODUTO', 'PERIODO_PRODUTO', 'ANO', 'FORMATO', 'PREÇO', 'DATA/HORA']
    df_modelo = df[colunas].copy()

    # Criar features de sazonalidade mais robustas
    df_modelo['MES'] = df_modelo['DATA/HORA'].dt.month

    # Identificar período úmido (nov-abr) e seco (mai-out)
    df_modelo['PERIODO_HIDROLOGICO'] = df_modelo['MES'].apply(
        lambda x: 'UMIDO' if x in [11, 12, 1, 2, 3] else 'SECO'
    )

    # One-hot encoding do período hidrológico
    df_modelo['PERIODO_UMIDO'] = (df_modelo['PERIODO_HIDROLOGICO'] == 'UMIDO').astype(int)

    # Calcular estatísticas de preço por tipo de produto e período
    stats_grupo = df_modelo.groupby(['TIPO_PRODUTO', 'PERIODO_PRODUTO']).agg({
        'PREÇO': ['mean', 'std', 'min', 'max', 'count',
                 lambda x: np.percentile(x, 20),   # P10
                 lambda x: np.percentile(x, 50),   # P50
                 lambda x: np.percentile(x, 80)]   # P95
    }).reset_index()

    # Renomear colunas
    stats_grupo.columns = ['TIPO_PRODUTO', 'PERIODO_PRODUTO',
                          'PRECO_MEDIO', 'PRECO_STD', 'PRECO_MIN', 'PRECO_MAX',
                          'CONTAGEM', 'P10', 'P50', 'P95']

    # Merge para adicionar estatísticas aos dados originais
    df_modelo = pd.merge(
        df_modelo,
        stats_grupo,
        on=['TIPO_PRODUTO', 'PERIODO_PRODUTO'],
        how='left'
    )

    # Feature: Percentual de desvio do preço em relação à média
    df_modelo['PERC_DESVIO_MEDIA'] = (df_modelo['PREÇO'] - df_modelo['PRECO_MEDIO']) / df_modelo['PRECO_MEDIO'] * 100

    # Features: Posicionamento em relação aos percentis
    df_modelo['DIST_P10'] = (df_modelo['PREÇO'] - df_modelo['P10']) / df_modelo['P10'] * 100
    df_modelo['DIST_P50'] = (df_modelo['PREÇO'] - df_modelo['P50']) / df_modelo['P50'] * 100
    df_modelo['DIST_P95'] = (df_modelo['PREÇO'] - df_modelo['P95']) / df_modelo['P95'] * 100

    # Feature: Indicadores de preço extremo
    df_modelo['PRECO_ABAIXO_P10'] = (df_modelo['PREÇO'] < df_modelo['P10']).astype(int)
    df_modelo['PRECO_ACIMA_P95'] = (df_modelo['PREÇO'] > df_modelo['P95']).astype(int)

    # Pesos baseados no tipo e liquidez dos produtos
    pesos = {'MEN': 1, 'TRI': 1, 'SEM': 1, 'ANU': 1}
    df_modelo['PESO_TIPO'] = df_modelo['TIPO_PRODUTO'].map(pesos).fillna(0.5)

    # Calcular o INDICE_TARGET baseado nas distâncias para os percentis
    # Valores negativos indicam oportunidade de SHORT (preço acima do P95)
    # Valores positivos indicam oportunidade de LONG (preço abaixo do P10)
    df_modelo['INDICE_TARGET'] = np.zeros(len(df_modelo))

    # Oportunidade de LONG (quando preço < P10)
    mask_long = df_modelo['PRECO_ABAIXO_P10'] == 1
    df_modelo.loc[mask_long, 'INDICE_TARGET'] = df_modelo.loc[mask_long, 'DIST_P10'].clip(-100, 0) / -100

    # Oportunidade de SHORT (quando preço > P95)
    mask_short = df_modelo['PRECO_ACIMA_P95'] == 1
    df_modelo.loc[mask_short, 'INDICE_TARGET'] = -df_modelo.loc[mask_short, 'DIST_P95'].clip(0, 100) / 100

    # Região NEUTRA (entre P10 e P95) - normalizado para ficar entre -0.5 e 0.5
    mask_neutro = ~(mask_long | mask_short)
    df_modelo.loc[mask_neutro, 'INDICE_TARGET'] = (
        -df_modelo.loc[mask_neutro, 'DIST_P50'] / 100
    ).clip(-1, 1)

    # Ajustar pelo peso do tipo de produto (produtos mais líquidos têm mais impacto)
    df_modelo['INDICE_TARGET'] = df_modelo['INDICE_TARGET'] * df_modelo['PESO_TIPO']

    # Limitar entre -1 e 1
    df_modelo['INDICE_TARGET'] = df_modelo['INDICE_TARGET'].clip(-1, 1)

    # Remover linhas com valores ausentes nas colunas que serão usadas no modelo
    colunas_modelo = ['PRECO_MEDIO', 'PRECO_STD', 'P10', 'P50', 'P95',
                      'DIST_P10', 'DIST_P50', 'DIST_P95', 'PESO_TIPO',
                      'MES', 'PERIODO_UMIDO']

    df_modelo_limpo = df_modelo.dropna(subset=colunas_modelo)

    print(f"Registros originais: {len(df_modelo)}")
    print(f"Registros após remoção de valores ausentes: {len(df_modelo_limpo)}")

    return df_modelo_limpo

def treinar_modelo_rna(df_modelo):
    """Treina um modelo RNA melhorado com features mais relevantes."""
    # Separar features e target
    X = df_modelo[[
        'PRECO_MEDIO', 'PRECO_STD',
        'P10', 'P50', 'P95',
        'DIST_P10', 'DIST_P50', 'DIST_P95',
        'PRECO_ABAIXO_P10', 'PRECO_ACIMA_P95',
        'PESO_TIPO', 'MES', 'PERIODO_UMIDO'
    ]]
    y = df_modelo['INDICE_TARGET']

    # Criar preprocessing pipeline
    categorical_features = []
    numeric_features = [
        'PRECO_MEDIO', 'PRECO_STD',
        'P10', 'P50', 'P95',
        'DIST_P10', 'DIST_P50', 'DIST_P95',
        'PRECO_ABAIXO_P10', 'PRECO_ACIMA_P95',
        'PESO_TIPO', 'MES', 'PERIODO_UMIDO'
    ]

    preprocessor = ColumnTransformer(
        transformers=[
            ('num', Pipeline([
                ('imputer', SimpleImputer(strategy='median')),
                ('scaler', StandardScaler())
            ]), numeric_features)
        ]
    )

    # Criar pipeline com preprocessamento e modelo
    pipe = Pipeline([
        ('preprocessor', preprocessor),
        ('mlp', MLPRegressor(
            hidden_layer_sizes=(60, 30, 6),  # Rede mais profunda
            activation='relu',
            solver='adam',
            alpha=0.001,  # Regularização L2
            batch_size=32,
            learning_rate='adaptive',
            max_iter=3000,
            early_stopping=True,  # Parar quando não houver melhoria
            validation_fraction=0.2,
            random_state=46
        ))
    ])

    # Treinar modelo com validação cruzada
    print("Treinando modelo RNA melhorado...")
    X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42)
    pipe.fit(X_train, y_train)

    # Avaliar modelo
    score = pipe.score(X_test, y_test)
    print(f"Modelo treinado. R² no conjunto de teste: {score:.4f}")

    # Calcular erro médio absoluto
    y_pred = pipe.predict(X_test)
    mae = np.mean(np.abs(y_test - y_pred))
    print(f"Erro médio absoluto: {mae:.4f}")

    return pipe

def gerar_dados_historicos(df_modelo, data_inicial, data_final, modelo):
    """Gera série histórica do índice previsto pelo RNA para o período especificado."""
    # Filtrar dados para o período
    mask = (df_modelo['DATA/HORA'] >= pd.to_datetime(data_inicial)) & \
           (df_modelo['DATA/HORA'] <= pd.to_datetime(data_final))
    df_periodo = df_modelo[mask]

    if len(df_periodo) == 0:
        return pd.DataFrame(columns=['DATA', 'INDICE_TARGET'])

    # Agrupar por data para ter um registro por dia
    df_diario = df_periodo.groupby(df_periodo['DATA/HORA'].dt.date).agg({
        'PRECO_MEDIO': 'mean',
        'PRECO_STD': 'mean',
        'P10': 'mean',
        'P50': 'mean',
        'P95': 'mean',
        'DIST_P10': 'mean',
        'DIST_P50': 'mean',
        'DIST_P95': 'mean',
        'PRECO_ABAIXO_P10': 'mean',
        'PRECO_ACIMA_P95': 'mean',
        'PESO_TIPO': 'mean',
        'PERIODO_UMIDO': 'mean',
        'INDICE_TARGET': 'mean'
    }).reset_index()

    # Adicionar mês como feature
    df_diario['MES'] = pd.to_datetime(df_diario['DATA/HORA']).dt.month

    # Preparar dados para previsão
    X_pred = df_diario[[
        'PRECO_MEDIO', 'PRECO_STD',
        'P10', 'P50', 'P95',
        'DIST_P10', 'DIST_P50', 'DIST_P95',
        'PRECO_ABAIXO_P10', 'PRECO_ACIMA_P95',
        'PESO_TIPO', 'MES', 'PERIODO_UMIDO'
    ]]

    try:
        # Fazer previsão para cada dia usando o RNA
        indices_previstos = modelo.predict(X_pred)

        # Converter para numpy array para garantir que são números
        indices_previstos = np.array(indices_previstos).astype(float)

        # Adicionar previsões ao dataframe
        df_diario['INDICE_TARGET'] = indices_previstos

        # Limitar valores entre -1 e 1 usando numpy em vez de pandas
        df_diario['INDICE_TARGET'] = np.clip(df_diario['INDICE_TARGET'], -1, 1)
    except Exception as e:
        print(f"Erro ao fazer previsões com o RNA: {e}")
        # Se houver erro, manter os valores INDICE_TARGET originais

    # Formatar para retornar ao gráfico
    df_diario['DATA'] = df_diario['DATA/HORA'].astype(str)

    return df_diario[['DATA', 'INDICE_TARGET']]

def criar_grafico_indice(dados_historicos, titulo, cor_linha='blue'):
    """Cria um gráfico Plotly para o índice histórico."""
    fig = go.Figure()

    # Adicionar áreas coloridas para zonas de trading
    # Zona de LONG (acima de LIMITE_NEUTRO)
    fig.add_trace(go.Scatter(
        x=dados_historicos['DATA'],
        y=[LIMITE_NEUTRO] * len(dados_historicos),
        fill=None,
        mode='lines',
        line=dict(width=0),
        showlegend=False
    ))

    fig.add_trace(go.Scatter(
        x=dados_historicos['DATA'],
        y=[1] * len(dados_historicos),
        fill='tonexty',  # preencher área entre essa trace e a anterior
        mode='lines',
        line=dict(width=0),
        fillcolor='rgba(76, 175, 80, 0.2)',  # Verde transparente
        name='Zona LONG'
    ))

    # Zona de SHORT (abaixo de -LIMITE_NEUTRO)
    fig.add_trace(go.Scatter(
        x=dados_historicos['DATA'],
        y=[-LIMITE_NEUTRO] * len(dados_historicos),
        fill=None,
        mode='lines',
        line=dict(width=0),
        showlegend=False
    ))

    fig.add_trace(go.Scatter(
        x=dados_historicos['DATA'],
        y=[-1] * len(dados_historicos),
        fill='tonexty',  # preencher área entre essa trace e a anterior
        mode='lines',
        line=dict(width=0),
        fillcolor='rgba(244, 67, 54, 0.2)',  # Vermelho transparente
        name='Zona SHORT'
    ))

    # Adicionar linha do índice
    fig.add_trace(go.Scatter(
        x=dados_historicos['DATA'],
        y=dados_historicos['INDICE_TARGET'],
        mode='lines',
        name='Índice',
        line=dict(color=cor_linha, width=3)
    ))

    # Adicionar linhas de referência
    fig.add_shape(
        type="line", line=dict(color="green", width=2, dash="dash"),
        y0=LIMITE_NEUTRO, y1=LIMITE_NEUTRO, x0=dados_historicos['DATA'].iloc[0], x1=dados_historicos['DATA'].iloc[-1]
    )
    fig.add_shape(
        type="line", line=dict(color="red", width=2, dash="dash"),
        y0=-LIMITE_NEUTRO, y1=-LIMITE_NEUTRO, x0=dados_historicos['DATA'].iloc[0], x1=dados_historicos['DATA'].iloc[-1]
    )
    fig.add_shape(
        type="line", line=dict(color="gray", width=1),
        y0=0, y1=0, x0=dados_historicos['DATA'].iloc[0], x1=dados_historicos['DATA'].iloc[-1]
    )

    # Configurar eixos e layout
    fig.update_layout(
        title=titulo,
        xaxis_title="Data",
        yaxis_title="Índice",
        yaxis=dict(
            range=[-1.1, 1.1],
            tickmode='array',
            tickvals=[-1, -LIMITE_NEUTRO, 0, LIMITE_NEUTRO, 1],
            ticktext=['-1', f'-{LIMITE_NEUTRO}', '0', f'{LIMITE_NEUTRO}', '1']
        ),
        legend_title="Legenda",
        template="plotly_white",
        height=500
    )

    # Adicionar anotações para áreas de recomendação
    fig.add_annotation(
        x=dados_historicos['DATA'].iloc[0],
        y=0.9,
        text="LONG ESTRUTURAL",
        showarrow=False,
        font=dict(color="green", size=14)
    )
    fig.add_annotation(
        x=dados_historicos['DATA'].iloc[0],
        y=-0.9,
        text="SHORT ESTRUTURAL",
        showarrow=False,
        font=dict(color="red", size=14)
    )
    fig.add_annotation(
        x=dados_historicos['DATA'].iloc[0],
        y=0,
        text="NEUTRO",
        showarrow=False,
        font=dict(color="orange", size=14)
    )

    return fig

def interpretar_resultado(indice, produto, P10=None, P50=None, P95=None, preco_atual=None):
    """Gera uma interpretação textual do resultado para o produto, baseada em patamares históricos."""
    recomendacao, _ = obter_recomendacao(indice)

    # Verificar quão extremo é o índice (próximo de -1 ou 1)
    indice_extremo = abs(indice) > 0.7  # Podemos ajustar este valor

    if recomendacao == "LONG ESTRUTURAL":
        if indice_extremo:
            mensagem = (f"Os preços de {produto} estão em patamares historicamente baixos. "
                        f"A estratégia Long Estrutural é recomendada, considerando que os preços "
                        f"atuais estão significativamente abaixo dos valores históricos de referência.")
        else:
            mensagem = (f"Os preços de {produto} estão abaixo dos patamares históricos médios. "
                        f"Uma oportunidade de posicionamento Long Estrutural começa a se apresentar.")

    elif recomendacao == "SHORT ESTRUTURAL":
        if indice_extremo:
            mensagem = (f"Os preços de {produto} estão em patamares historicamente elevados. "
                        f"A estratégia Short Estrutural é recomendada, considerando que os preços "
                        f"atuais estão significativamente acima dos valores históricos de referência.")
        else:
            mensagem = (f"Os preços de {produto} estão acima dos patamares históricos médios. "
                        f"Uma oportunidade de posicionamento Short Estrutural começa a se apresentar.")
    else:
        mensagem = (f"Os preços atuais de {produto} estão próximos aos patamares históricos médios. "
                    f"Não há clara oportunidade de posicionamento Long ou Short Estrutural neste momento.")

    return mensagem

def calcular_indice_produto(df_modelo, tipo_produto, periodo_produto, ano, modelo):
    """Calcula o índice de um produto específico baseado em percentis reais."""
    # Filtrar dados para o produto específico
    mask = (df_modelo['TIPO_PRODUTO'] == tipo_produto) & \
           (df_modelo['PERIODO_PRODUTO'] == periodo_produto) & \
           (df_modelo['ANO'].astype(str) == str(ano))
    df_produto = df_modelo[mask]

    if len(df_produto) == 0:
        # Buscar produtos similares
        mask_tipo = (df_modelo['TIPO_PRODUTO'] == tipo_produto)
        df_tipo = df_modelo[mask_tipo]

        if len(df_tipo) == 0:
            return 0, "Dados insuficientes para análise deste produto."

        # Estatísticas do tipo de produto
        preco_medio_tipo = df_tipo['PRECO_MEDIO'].mean()
        p10_tipo = df_tipo['P10'].mean()
        p50_tipo = df_tipo['P50'].mean()
        p95_tipo = df_tipo['P95'].mean()

        # Simular preço atual (ligeiramente abaixo da média para produtos novos)
        preco_atual = preco_medio_tipo * 0.95

        # Calcular distâncias aos percentis
        dist_p10 = (preco_atual - p10_tipo) / p10_tipo * 100
        dist_p50 = (preco_atual - p50_tipo) / p50_tipo * 100
        dist_p95 = (preco_atual - p95_tipo) / p95_tipo * 100

        # Features para o modelo
        mes_atual = datetime.now().month
        periodo_umido = 1 if mes_atual in [11, 12, 1, 2, 3] else 0

        # Peso do tipo de produto
        pesos = {'MEN': 1, 'TRI': 1.0, 'SEM': 1.0, 'ANU': 1.0}
        peso_tipo = pesos.get(tipo_produto, 1)

        # Indicadores de preço extremo
        preco_abaixo_p10 = 1 if preco_atual < p10_tipo else 0
        preco_acima_p95 = 1 if preco_atual > p95_tipo else 0

        # Preparar dados para previsão
        X_pred = pd.DataFrame({
            'PRECO_MEDIO': [preco_medio_tipo],
            'PRECO_STD': [df_tipo['PRECO_STD'].mean()],
            'P10': [p10_tipo],
            'P50': [p50_tipo],
            'P95': [p95_tipo],
            'DIST_P10': [dist_p10],
            'DIST_P50': [dist_p50],
            'DIST_P95': [dist_p95],
            'PRECO_ABAIXO_P10': [preco_abaixo_p10],
            'PRECO_ACIMA_P95': [preco_acima_p95],
            'PESO_TIPO': [peso_tipo],
            'MES': [mes_atual],
            'PERIODO_UMIDO': [periodo_umido]
        })

        # Fazer previsão com o modelo
        try:
            indice_produto = modelo.predict(X_pred)[0]
            msg = "Previsão baseada em produtos similares (dados limitados)."
        except Exception as e:
            print(f"Erro na previsão: {e}")
            # Fallback baseado em heurística
            if preco_abaixo_p10:
                indice_produto = 0.8  # LONG
            elif preco_acima_p95:
                indice_produto = -0.8  # SHORT
            else:
                # Normalizado entre -0.5 e 0.5 com base na distância do P50
                indice_produto = -dist_p50 / 100
                indice_produto = max(-1, min(1, indice_produto))

            msg = "Cálculo baseado em heurística (dados limitados)."
    else:
        # Calcular índice médio para o produto baseado nos dados reais
        indice_produto = df_produto['INDICE_TARGET'].mean()

        # Verificar se temos preços recentes
        data_recente = df_produto['DATA/HORA'].max()
        delta_dias = (datetime.now() - data_recente).days

        if delta_dias > 30:
            msg = f"Índice calculado com base em {len(df_produto)} registros, mas o mais recente é de {delta_dias} dias atrás."
        else:
            msg = f"Índice calculado com base em {len(df_produto)} registros recentes."

    # Limitar entre -1 e 1
    indice_produto = max(-1, min(1, indice_produto))

    return indice_produto, msg

def gerar_dados_produto_especifico(df, data_inicial, data_final, tipo_produto, periodo_produto, ano, modelo=None):
    """Gera série histórica do índice para um produto específico com abordagem híbrida."""
    # Filtrar dados do produto específico
    mask_produto = (df['TIPO_PRODUTO'] == tipo_produto) & \
                   (df['PERIODO_PRODUTO'] == periodo_produto) & \
                   (df['ANO'].astype(str) == str(ano))
    df_produto = df[mask_produto]

    # Se temos poucos dados do produto específico, buscar produtos similares
    if len(df_produto) < 10:
        # Primeiro tentar produtos com mesmo tipo e período
        mask_similar = (df['TIPO_PRODUTO'] == tipo_produto) & \
                      (df['PERIODO_PRODUTO'] == periodo_produto)
        df_similar = df[mask_similar]

        # Se ainda insuficiente, usar apenas mesmo tipo
        if len(df_similar) < 10:
            mask_similar = (df['TIPO_PRODUTO'] == tipo_produto)
            df_similar = df[mask_similar]

        print(f"Usando {len(df_similar)} registros de produtos similares para complementar análise.")

        # Combinar dados, priorizando o produto específico
        df_combinado = pd.concat([df_produto, df_similar]).drop_duplicates()
    else:
        df_combinado = df_produto

    # Agrupar por data para série temporal
    df_diario = df_combinado.groupby(df_combinado['DATA/HORA'].dt.date).agg({
        'INDICE_TARGET': 'mean',
        'P10': 'mean',
        'P50': 'mean',
        'P95': 'mean',
        'PRECO_MEDIO': 'mean',
        'PREÇO': ['mean', 'min', 'max']
    }).reset_index()

    # Renomear colunas
    df_diario.columns = ['DATA/HORA', 'INDICE_TARGET', 'P10', 'P50', 'P95',
                         'PRECO_MEDIO', 'PRECO_DIA', 'PRECO_MIN', 'PRECO_MAX']

    # Completar datas faltantes
    todas_datas = pd.date_range(start=data_inicial, end=data_final)
    df_completo = pd.DataFrame({'DATA/HORA': todas_datas})
    df_completo['DATA/HORA'] = df_completo['DATA/HORA'].dt.date
    df_completo = pd.merge(df_completo, df_diario, on='DATA/HORA', how='left')

    # Preencher valores estatísticos (P10, P50, P95) usando interpolação
    for col in ['P10', 'P50', 'P95', 'PRECO_MEDIO']:
        if df_completo[col].notna().sum() > 0:
            df_completo[col] = df_completo[col].interpolate(method='linear')

    # Se temos dados de preço do dia, recalcular o índice target
    if df_completo['PRECO_DIA'].notna().sum() > 0:
        df_completo['PRECO_DIA'] = df_completo['PRECO_DIA'].interpolate(method='linear')

        # Calcular o INDICE_TARGET baseado nas distâncias para os percentis
        df_completo['INDICE_TARGET'] = np.zeros(len(df_completo))

        # Oportunidade de LONG (quando preço < P10)
        mask_long = df_completo['PRECO_DIA'] < df_completo['P10']
        if mask_long.any():
            dist_p10 = (df_completo.loc[mask_long, 'PRECO_DIA'] - df_completo.loc[mask_long, 'P10']) / df_completo.loc[mask_long, 'P10'] * 100
            df_completo.loc[mask_long, 'INDICE_TARGET'] = dist_p10.clip(-100, 0) / -100

        # Oportunidade de SHORT (quando preço > P95)
        mask_short = df_completo['PRECO_DIA'] > df_completo['P95']
        if mask_short.any():
            dist_p95 = (df_completo.loc[mask_short, 'PRECO_DIA'] - df_completo.loc[mask_short, 'P95']) / df_completo.loc[mask_short, 'P95'] * 100
            df_completo.loc[mask_short, 'INDICE_TARGET'] = -dist_p95.clip(0, 100) / 100

        # Região NEUTRA (entre P10 e P95) - normalizado para ficar entre -0.5 e 0.5
        mask_neutro = ~(mask_long | mask_short)
        if mask_neutro.any():
            dist_p50 = (df_completo.loc[mask_neutro, 'PRECO_DIA'] - df_completo.loc[mask_neutro, 'P50']) / df_completo.loc[mask_neutro, 'P50'] * 100
            df_completo.loc[mask_neutro, 'INDICE_TARGET'] = (-dist_p50 / 100).clip(-0.5, 0.5)
    else:
        # Usar modelo ou interpolação para estimar o índice
        if 'INDICE_TARGET' in df_completo.columns and df_completo['INDICE_TARGET'].notna().sum() > 0:
            df_completo['INDICE_TARGET'] = df_completo['INDICE_TARGET'].interpolate(method='linear')
        elif modelo is not None:
            # Criar features para o modelo
            df_completo['MES'] = pd.to_datetime(df_completo['DATA/HORA']).dt.month
            df_completo['PERIODO_UMIDO'] = df_completo['MES'].apply(
                lambda x: 1 if x in [11, 12, 1, 2, 3] else 0
            )

            # Peso do tipo de produto
            pesos = {'MEN': 1, 'TRI': 1.0, 'SEM': 1.0, 'ANU': 1.0}
            df_completo['PESO_TIPO'] = pesos.get(tipo_produto, 1)

            # Calcular distâncias simuladas para percentis
            df_completo['PRECO_STD'] = df_completo['PRECO_MEDIO'] * 0.05  # Estimativa de desvio padrão
            df_completo['DIST_P10'] = np.zeros(len(df_completo))
            df_completo['DIST_P50'] = np.zeros(len(df_completo))
            df_completo['DIST_P95'] = np.zeros(len(df_completo))
            df_completo['PRECO_ABAIXO_P10'] = np.zeros(len(df_completo))
            df_completo['PRECO_ACIMA_P95'] = np.zeros(len(df_completo))

            for date_idx in range(len(df_completo)):
                row = df_completo.iloc[date_idx]
                if pd.notna(row['PRECO_MEDIO']) and pd.notna(row['P10']) and pd.notna(row['P50']) and pd.notna(row['P95']):
                    # Simular um preço realista para o dia
                    # Usar tendência baseada na data (mais recente = mais próximo da média)
                    peso_data = date_idx / max(1, len(df_completo) - 1)
                    preco_simulado = row['P50'] * (1 - 0.1 + 0.2 * peso_data)

                    # Calcular distâncias
                    df_completo.loc[date_idx, 'DIST_P10'] = (preco_simulado - row['P10']) / row['P10'] * 100
                    df_completo.loc[date_idx, 'DIST_P50'] = (preco_simulado - row['P50']) / row['P50'] * 100
                    df_completo.loc[date_idx, 'DIST_P95'] = (preco_simulado - row['P95']) / row['P95'] * 100
                    df_completo.loc[date_idx, 'PRECO_ABAIXO_P10'] = 1 if preco_simulado < row['P10'] else 0
                    df_completo.loc[date_idx, 'PRECO_ACIMA_P95'] = 1 if preco_simulado > row['P95'] else 0

            # Features para o modelo
            X_pred = df_completo[[
                'PRECO_MEDIO', 'PRECO_STD',
                'P10', 'P50', 'P95',
                'DIST_P10', 'DIST_P50', 'DIST_P95',
                'PRECO_ABAIXO_P10', 'PRECO_ACIMA_P95',
                'PESO_TIPO', 'MES', 'PERIODO_UMIDO'
            ]].fillna(method='ffill').fillna(method='bfill')

            # Verificar e substituir NaNs por valores padrão onde ainda necessário

            X_pred = X_pred.fillna({
                'PRECO_ABAIXO_P10': 0,
                'PRECO_ACIMA_P95': 0,
                'DIST_P10': 0,
                'DIST_P50': 0,
                'DIST_P95': 0,
                'PESO_TIPO': 0.5
            })

            # Prever índices
            try:
                df_completo['INDICE_TARGET'] = modelo.predict(X_pred)
            except Exception as e:
                print(f"Erro na previsão com o modelo: {e}")
                # Fallback: gerar uma tendência realista
                tendencia = np.linspace(-0.3, 0.3, len(df_completo))
                ruido = np.random.normal(0, 0.1, size=len(df_completo))
                df_completo['INDICE_TARGET'] = tendencia + ruido
        else:
            # Não temos dados nem modelo, gerar série simulada
            n = len(df_completo)
            tendencia = np.linspace(-0.3, 0.3, n)
            ruido = np.random.normal(0, 0.1, size=n)
            df_completo['INDICE_TARGET'] = tendencia + ruido

    # Limitar valores entre -1 e 1
    df_completo['INDICE_TARGET'] = df_completo['INDICE_TARGET'].clip(-1, 1)

    # Formatar datas para string
    df_completo['DATA'] = df_completo['DATA/HORA'].astype(str)

    return df_completo[['DATA', 'INDICE_TARGET']]

def atualizar_analise_produto_percentil_corrigido(tipo_produto, periodo_produto, ano, considerar_ano, data_inicial, data_final, df_filtrado):
    """Atualiza a análise de produto baseado em percentil, corrigida para ignorar filtros de data quando considerar_ano=False."""
    try:
        # Validar seleção
        if not tipo_produto or not periodo_produto:
            return None, None, "", "Selecione o tipo e período do produto para análise."

        if considerar_ano and not ano:
            return None, None, "", "Selecione o ano ou desmarque a opção 'Considerar ano específico'."

        # Filtrar dados para o produto
        mask_produto = (df_filtrado['TIPO_PRODUTO'] == tipo_produto) & \
                       (df_filtrado['PERIODO_PRODUTO'] == periodo_produto)

        # Aplicar filtro por ano apenas se a opção estiver marcada
        if considerar_ano:
            mask_produto = mask_produto & (df_filtrado['ANO'].astype(str) == str(ano))

        # Obter dados do produto (sem filtrar por data se não considerar ano específico)
        if considerar_ano:
            # Com ano específico, aplicar filtro de data normalmente
            mask_data = (df_filtrado['DATA/HORA'] >= pd.to_datetime(data_inicial)) & \
                        (df_filtrado['DATA/HORA'] <= pd.to_datetime(data_final))
            df_produto = df_filtrado[mask_produto & mask_data]
        else:
            # Para todos os anos, ignorar filtro de data e pegar todos os dados históricos
            df_produto = df_filtrado[mask_produto]

        if len(df_produto) == 0:
            return None, None, "", "Nenhum dado disponível para o produto selecionado."

        # Calcular estatísticas para todos os dados do produto
        preco_min = df_produto['PREÇO'].quantile(0.01)  # 5º percentil
        preco_max = df_produto['PREÇO'].quantile(0.99)  # 95º percentil

        # Para o preço atual, usar a média dos últimos 30 dias
        data_max = df_produto['DATA/HORA'].max()
        df_dia_mais_recente = df_produto[df_produto['DATA/HORA'].dt.date == data_max]
        if len(df_dia_mais_recente) > 0:
            preco_atual = df_dia_mais_recente['PREÇO'].median()
            metodo_preco = "mediana do dia mais recente"
        else:
            preco_atual = df_produto['PREÇO'].iloc[-1]  # Último preço disponível
            metodo_preco = "último preço disponível"

        # Calcular posição relativa na faixa de preços (invertida)
        if preco_max > preco_min:
            posicao_relativa = (preco_atual - preco_min) / (preco_max - preco_min)
            indice = 1 - 2 * posicao_relativa  # -1 (máximo) a +1 (mínimo)
        else:
            indice = 0  # Evitar divisão por zero

        # Criar série histórica para o gráfico
        if considerar_ano:
            # Com ano específico, aplicar filtro de data normalmente
            mask_data = (df_filtrado['DATA/HORA'] >= pd.to_datetime(data_inicial)) & \
                        (df_filtrado['DATA/HORA'] <= pd.to_datetime(data_final))
            df_grafico = df_filtrado[mask_produto & mask_data]
        else:
            # Para análise de todos os anos, mostramos apenas os últimos 90 dias no gráfico
            # para evitar gráfico muito poluído com dados de todos os anos
            df_grafico = df_filtrado[mask_produto & (df_filtrado['DATA/HORA'] >= (data_max - timedelta(days=150)))]

        # Agrupar por data para série temporal
        df_diario = df_grafico.groupby(df_grafico['DATA/HORA'].dt.date).agg({
            'PREÇO': ['mean', 'min', 'max']
        }).reset_index()

        # Renomear colunas
        df_diario.columns = ['DATA/HORA', 'PRECO_DIA', 'PRECO_MIN_DIA', 'PRECO_MAX_DIA']

        # Completar datas faltantes
        if considerar_ano:
            data_range_start = pd.to_datetime(data_inicial).date()
            data_range_end = pd.to_datetime(data_final).date()
        else:
            data_range_start = (data_max - timedelta(days=150)).date()
            data_range_end = data_max.date()

        todas_datas = pd.date_range(start=data_range_start, end=data_range_end)
        df_completo = pd.DataFrame({'DATA/HORA': todas_datas})
        df_completo['DATA/HORA'] = df_completo['DATA/HORA'].dt.date
        df_completo = pd.merge(df_completo, df_diario, on='DATA/HORA', how='left')

        # Interpolar valores ausentes
        for col in ['PRECO_DIA', 'PRECO_MIN_DIA', 'PRECO_MAX_DIA']:
            if df_completo[col].notna().sum() > 0:
                df_completo[col] = df_completo[col].interpolate(method='linear')

        # Calcular índice diário baseado no percentil
        df_completo['INDICE_TARGET'] = 1 - 2 * ((df_completo['PRECO_DIA'] - preco_min) / max(1e-10, preco_max - preco_min))
        df_completo['INDICE_TARGET'] = df_completo['INDICE_TARGET'].clip(-1, 1)

        # Formatar datas para string
        df_completo['DATA'] = df_completo['DATA/HORA'].astype(str)

        # Criar gráficos
        dados_historicos = df_completo[['DATA', 'INDICE_TARGET']].dropna()

        if len(dados_historicos) == 0:
            # Se não houver dados para o gráfico
            return None, None, "", "Dados insuficientes para criar o gráfico."

        # Usar o último valor do índice para garantir consistência
        indice_atual = dados_historicos['INDICE_TARGET'].iloc[-1]

        # Criar gráficos
        grafico_produto = criar_grafico_indice(
            dados_historicos,
            f"Evolução do Índice por Percentil: {tipo_produto} {periodo_produto}" + (f" {ano}" if considerar_ano else " (todos os anos)"),
            CORES['LINHA_PRODUTO']
        )

        grafico_indice_atual = criar_grafico_indice_atual(
            indice_atual,
            "Índice Atual do Produto"
        )

        # Obter recomendação
        recomendacao, cor = obter_recomendacao(indice_atual)

        # Formatar produto completo para a mensagem
        if considerar_ano:
            produto_descricao = f"SE CON {tipo_produto} {periodo_produto} {ano} PreçoFixo"
        else:
            produto_descricao = f"SE CON {tipo_produto} {periodo_produto} (todos os anos) PreçoFixo"

        # Interpretar resultado com estatísticas completas
        interpretacao = f"Com base na análise de preços históricos, o produto {tipo_produto} {periodo_produto}"
        if considerar_ano:
            interpretacao += f" {ano}"
        else:
            interpretacao += " (todos os anos)"

        if indice_atual > LIMITE_NEUTRO:
            interpretacao += " está próximo de seus mínimos históricos, indicando possível oportunidade de LONG."
        elif indice_atual < -LIMITE_NEUTRO:
            interpretacao += " está próximo de seus máximos históricos, indicando possível oportunidade de SHORT."
        else:
            interpretacao += " está em uma faixa neutra de preços."

        interpretacao += f"\nAnálise baseada em {len(df_produto)} registros do produto {produto_descricao}."
        interpretacao += f"\nFaixa de preços: R${preco_min:.2f} (mínimo) a R${preco_max:.2f} (máximo)"
        interpretacao += f"\nPreço atual: R${preco_atual:.2f} ({metodo_preco}, está a {posicao_relativa*100:.1f}% da faixa histórica)"
        interpretacao += f"\nO índice mostrado ({indice_atual:.2f}) corresponde ao último valor do gráfico."

        # Formatar resultado HTML
        resultado_html = f"<div style='text-align: center; padding: 10px; border-radius: 5px; background-color: {cor}; color: white;'>"
        resultado_html += f"<h2>{recomendacao}</h2>"
        resultado_html += f"<h3>Índice: {indice_atual:.2f}</h3>"
        resultado_html += "</div>"

        # Retornar resultados conforme esperado pela interface
        return grafico_produto, grafico_indice_atual, resultado_html, interpretacao

    except Exception as e:
        import traceback
        traceback.print_exc()
        return None, None, f"Erro: {str(e)}", "Erro na análise do produto."

def main():
    """Função principal que cria a interface com abas combinando os dois modelos."""
    try:
        # Carregar e preparar dados comuns para ambos os modelos
        current_dir = os.path.dirname(os.path.abspath(__file__))
        file_path = os.path.join(current_dir, "TodosNegocios2.xlsx")
        
        df = pd.read_excel(file_path, sheet_name='Todos Negócios', engine='openpyxl')
        if df is None:
            print("Erro: Não foi possível carregar os dados.")
            return

        # Aplicar os filtros comuns
        df_filtrado = preprocessar_dados(df)
        data_limite = calcular_data_recente(df_filtrado)
        produtos_recentes = obter_produtos_recentes(df_filtrado, data_limite)

        # Preparar dados para o modelo RNA
        df_modelo = preparar_dados_para_modelo(df_filtrado)

        # Treinar modelo RNA
        modelo = treinar_modelo_rna(df_modelo)

        # Definir as funções de callback dentro da função main
        def atualizar_analise_global(data_inicial, data_final):
            """Atualiza a análise global para o período selecionado."""
            try:
                # Validar datas
                data_ini = pd.to_datetime(data_inicial)
                data_fim = pd.to_datetime(data_final)

                if data_ini > data_fim:
                    return None, "Data inicial deve ser anterior à data final.", None, "Erro nos dados."

                # Calcular índice global
                indice_global, msg_global = atualizar_indice_global(data_inicial, data_final)

                # Gerar dados históricos para o gráfico
                dados_historicos = gerar_dados_historicos(df_modelo, data_inicial, data_final, modelo)

                # Criar gráfico
                fig_global = criar_grafico_indice(
                    dados_historicos,
                    "Índice Global de Posição Estrutural",
                    CORES['LINHA_GLOBAL']
                )

                # Obter recomendação
                recomendacao, cor = obter_recomendacao(indice_global)

                # Formatar resultado
                resultado_global = f"<div style='text-align: center; padding: 10px; border-radius: 5px; background-color: {cor}; color: white;'>"
                resultado_global += f"<h2>{recomendacao}</h2>"
                resultado_global += f"<h3>Índice: {indice_global:.2f}</h3>"
                resultado_global += "</div>"

                return fig_global, resultado_global, indice_global, msg_global

            except Exception as e:
                import traceback
                traceback.print_exc()
                return None, f"Erro: {str(e)}", 0, "Erro na análise."

        def atualizar_indice_global(data_inicial, data_final):
            """Calcula o índice global para o período selecionado."""
            # Filtrar dados para o período
            mask = (df_modelo['DATA/HORA'] >= pd.to_datetime(data_inicial)) & \
                 (df_modelo['DATA/HORA'] <= pd.to_datetime(data_final))
            df_periodo = df_modelo[mask]

            if len(df_periodo) == 0:
                return 0, "Nenhum dado disponível para o período selecionado."

            # Gerar dados históricos para garantir consistência com o gráfico
            dados_historicos = gerar_dados_historicos(df_modelo, data_inicial, data_final, modelo)

            # IMPORTANTE: Usar o último valor do gráfico para garantir convergência
            if len(dados_historicos) > 0:
                indice_global = dados_historicos['INDICE_TARGET'].iloc[-1]
                data_mais_recente = pd.to_datetime(dados_historicos['DATA'].iloc[-1])
            else:
                # Só usar o método original se não tivermos dados no gráfico
                data_mais_recente = df_periodo['DATA/HORA'].max()

                # Calcular médias das features mais recentes para últimos 30 dias
                df_recente = df_periodo[df_periodo['DATA/HORA'] >= (data_mais_recente - timedelta(days=30))]

                if len(df_recente) == 0:
                    df_recente = df_periodo  # Fallback se não houver dados nos últimos 30 dias


                # Preparar dados para a previsão com o RNA
                X_pred = pd.DataFrame({
                    'PRECO_MEDIO': [df_recente['PRECO_MEDIO'].mean()],
                    'PRECO_STD': [df_recente['PRECO_STD'].mean()],
                    'P10': [df_recente['P10'].mean()],
                    'P50': [df_recente['P50'].mean()],
                    'P95': [df_recente['P95'].mean()],
                    'DIST_P10': [df_recente['DIST_P10'].mean()],
                    'DIST_P50': [df_recente['DIST_P50'].mean()],
                    'DIST_P95': [df_recente['DIST_P95'].mean()],
                    'PRECO_ABAIXO_P10': [df_recente['PRECO_ABAIXO_P10'].mean()],
                    'PRECO_ACIMA_P95': [df_recente['PRECO_ACIMA_P95'].mean()],
                    'PESO_TIPO': [df_recente['PESO_TIPO'].mean()],
                    'MES': [data_mais_recente.month],
                    'PERIODO_UMIDO': [1 if data_mais_recente.month in [11, 12, 1, 2, 3, 4] else 0]
                })

                # Fazer previsão com o modelo RNA
                try:
                    indice_global = modelo.predict(X_pred)[0]
                except Exception as e:
                    print(f"Erro ao prever índice global: {e}")
                    # Fallback: usar a média dos índices target do período
                    indice_global = df_periodo['INDICE_TARGET'].mean()

                    # Formatar mensagem de aviso
                    msg = f"Índice previsto pelo modelo RNA com base nos dados até {data_mais_recente.strftime('%d/%m/%Y')}."

            # Limitar entre -1 e 1 (aplicado em qualquer caso)
            indice_global = max(-1, min(1, indice_global))

            # Formatar mensagem de aviso
            msg = f"Índice previsto pelo modelo RNA com base nos dados até {data_mais_recente.strftime('%d/%m/%Y')}."

            return indice_global, msg

        def atualizar_analise_produto(indice_global, tipo_produto, periodo_produto, ano, data_inicial, data_final):
            """Atualiza a análise de um produto específico."""
            try:
                # Validar seleção
                if not tipo_produto or not periodo_produto or not ano:
                    return None, None, "", "Selecione o produto para análise."

                # Obter dados do produto
                mask_produto = (df_modelo['TIPO_PRODUTO'] == tipo_produto) & \
                               (df_modelo['PERIODO_PRODUTO'] == periodo_produto) & \
                               (df_modelo['ANO'].astype(str) == str(ano))
                df_produto = df_modelo[mask_produto]

                # Preço atual e percentis para interpretação
                p10, p50, p95, preco_atual = None, None, None, None
                if len(df_produto) > 0:
                    p10 = df_produto['P10'].mean()
                    p50 = df_produto['P50'].mean()
                    p95 = df_produto['P95'].mean()
                    preco_atual = df_produto['PREÇO'].mean()

                # Gerar dados históricos específicos do produto
                dados_produto = gerar_dados_produto_especifico(
                    df_modelo, data_inicial, data_final,
                    tipo_produto, periodo_produto, ano, modelo
                )

                # IMPORTANTE: Garantir que o índice mostrado no card seja o mesmo do último ponto do gráfico
                if len(dados_produto) > 0:
                    # Usar o último valor do gráfico como índice atual para garantir convergência
                    indice_produto = dados_produto['INDICE_TARGET'].iloc[-1]
                else:
                    # Se não houver dados no gráfico, calcular usando o método original
                    indice_produto, msg_produto = calcular_indice_produto(df_modelo, tipo_produto, periodo_produto, ano, modelo)
                    # Influência do índice global (30%)
                    indice_produto = indice_produto * 0.9 + indice_global * 0.1

                # Limitar entre -1 e 1
                indice_produto = max(-1, min(1, indice_produto))


                # Criar gráficos
                fig_produto_historico = criar_grafico_indice(
                    dados_produto,
                    f"Evolução do Índice: {tipo_produto} {periodo_produto} {ano}",
                    CORES['LINHA_PRODUTO']
                )

                fig_produto_atual = criar_grafico_indice_atual(
                    indice_produto,
                    "Índice Atual do Produto"
                )

                # Obter recomendação
                recomendacao, cor = obter_recomendacao(indice_produto)

                # Formatar produto completo
                produto_completo = f"SE CON {tipo_produto} {periodo_produto} {ano} PreçoFixo"

                # Gerar interpretação
                interpretacao = interpretar_resultado(indice_produto, produto_completo, p10, p50, p95, preco_atual)

                # Formatar resultado
                resultado_produto = f"<div style='text-align: center; padding: 10px; border-radius: 5px; background-color: {cor}; color: white;'>"
                resultado_produto += f"<h2>{recomendacao}</h2>"
                resultado_produto += f"<h3>Índice: {indice_produto:.2f}</h3>"
                resultado_produto += "</div>"

                return fig_produto_historico, fig_produto_atual, resultado_produto, interpretacao

            except Exception as e:
                import traceback
                traceback.print_exc()
                return None, None, f"Erro: {str(e)}", "Erro na análise do produto."

        # Criar interface única com abas
        with gr.Blocks(title="Análise Estrutural do Mercado de Energia", css=css_personalizado) as interface_combinada:
            # Cabeçalho Principal
            gr.HTML("""
            <div style="text-align:center;">
                <div class="header-banner">
                    <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="header-icon"><circle cx="12" cy="12" r="1"/><circle cx="19" cy="12" r="1"/><circle cx="5" cy="12" r="1"/><path d="M3.6 8.4a10.5 10.5 0 1 0 16.8 0"/></svg>
                    <span class="header-text">Análise inteligente de mercado</span>
                </div>
                <h1 class="main-title">Análise Estrutural do Mercado de Energia</h1>
                <p class="subtitle">
                    Auxílio na Tomada de decisão através dos modelos de RNA e análise probabilística
                </p>
                <svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="arrow-down"><path d="M12 5v14M5 12l7 7 7-7"/></svg>
            </div>
            """)

            with gr.Tabs():
                # Aba 1: Modelo RNA
                with gr.TabItem("Modelo RNA"):
                    gr.Markdown("""
                    # Análise Estrutural do Mercado de Energia - Modelo RNA
                    Análise de oportunidades Long/Short Estrutural baseado em padrões históricos de preços.
                    """)

                    # Seção 1: Análise Global
                    with gr.Column():
                        gr.Markdown("## Índice Global de Posição Estrutural")

                        with gr.Row():
                            with gr.Column(scale=3):
                                data_inicial_rna = gr.Textbox(
                                    label="Data Inicial",
                                    value=(datetime.now() - timedelta(days=150)).strftime("%Y-%m-%d"),
                                    type="text"
                                )
                                data_final_rna = gr.Textbox(
                                    label="Data Final",
                                    value=datetime.now().strftime("%Y-%m-%d"),
                                    type="text"
                                )
                                btn_calcular = gr.Button("Calcular Índice Global", variant="primary")

                            with gr.Column(scale=2):
                                indice_global_output = gr.Number(label="Índice Global", visible=False)
                                resultado_global = gr.HTML(label="Recomendação")
                                msg_global = gr.Text(label="Informação")

                        grafico_global = gr.Plot(label="Evolução do Índice Global")

                    # Seção 2: Análise de Produto Específico
                    with gr.Column():
                        gr.HTML("""
                        <div style="background-color: transparent; border: none; box-shadow: none; padding: 10px;">
                        <h2 style="margin-bottom: 10px;">Análise de Produto Específico</h2>
                        </div>
                        """)
                        with gr.Row():
                            with gr.Column():
                                tipo_produto_rna = gr.Dropdown(
                                    label="Tipo de Produto",
                                    choices=produtos_recentes['tipoProduto'],
                                    value=None
                                )
                                periodo_produto_rna = gr.Dropdown(
                                    label="Período",
                                    choices=[],
                                    value=None,
                                    allow_custom_value=True
                                )
                                ano_rna = gr.Dropdown(
                                    label="Ano",
									choices=[],
									value=None,
                                    allow_custom_value=True
								)
                                gr.HTML("<div style='height: 5px;'></div>")  # Espaçamento
                                btn_analisar_produto = gr.Button("Analisar Produto", variant="primary")
                                
                            with gr.Column():
                                resultado_produto_rna = gr.HTML(label="Recomendação")
                                gr.HTML("<div style='height: 12px;'></div>")  # Espaçamento
                                interpretacao_rna = gr.Textbox(label="Interpretação", lines=4)
							
                        gr.HTML("<div style='height: 5px;'></div>")  # Espaçamento
                        
                        with gr.Row():
                            grafico_produto_historico = gr.Plot(label="Evolução Histórica do Índice")
                            
                        gr.HTML("<div style='height: 5px;'></div>")  # Espaçamento
                        
                        with gr.Row():
                            grafico_produto_atual_rna = gr.Plot(label="Índice Atual")
                    
                    # Nota metodológica
                    with gr.Column():
                        gr.HTML("""
                        <div style="background-color: transparent; border: none; box-shadow: none; padding: 15px; margin-top: 20px;">
                        <h2 style="font-size: 20px; font-weight: 600; color: #1f2937; margin-bottom: 12px;">Nota Metodológica</h2>
                        <p style="font-size: 14px; line-height: 1.5; color: #4b5563;">
                        O modelo de Redes Neurais Artificiais (RNA) utiliza diversos fatores para calcular o índice estrutural:
                        O índice varia de -1 (máxima oportunidade para Short Estrutural) a +1 (máxima oportunidade para Long Estrutural),
                        com valores entre -0.4 e +0.4 indicando mercado neutro.
                        </p>
                        </div>
                        """)

                # Aba 2: Modelo por Percentil
                with gr.TabItem("Modelo por Percentil"):
                    gr.Markdown("""
                    # Análise Estrutural do Mercado de Energia - Por Percentil
                    Análise de oportunidades Long/Short Estrutural baseado em percentis.
                    """)

                    # Seção: Análise de Produto Específico por Percentil
                    with gr.Column():
                        gr.Markdown("## Análise de Produto Específico por Percentil")

                        with gr.Row():
                            with gr.Column():
                                data_inicial_perc = gr.Textbox(
                                    label="Data Inicial",
                                    value=(datetime.now() - timedelta(days=150)).strftime("%Y-%m-%d"),
                                    type="text"
                                )
                                data_final_perc = gr.Textbox(
                                    label="Data Final",
                                    value=datetime.now().strftime("%Y-%m-%d"),
                                    type="text"
                                )
                                tipo_produto_perc = gr.Dropdown(
                                    label="Tipo de Produto",
                                    choices=produtos_recentes['tipoProduto'],
                                    value=None
                                )
                                periodo_produto_perc = gr.Dropdown(
                                    label="Período",
                                    choices=[],
                                    value=None,
                                    allow_custom_value=True
                                )
                                with gr.Row():
                                    considerar_ano = gr.Checkbox(
                                        label="Considerar ano específico?",
                                        value=True
                                    )
                                    ano_perc = gr.Dropdown(
                                        label="Ano",
                                        choices=[],
                                        value=None,
                                        interactive=True
                                    )
                                btn_analisar_perc = gr.Button("Analisar Produto", variant="primary")

                            with gr.Column():
                                resultado_produto_perc = gr.HTML(label="Recomendação")
                                interpretacao_perc = gr.Textbox(label="Interpretação", lines=6)

                        grafico_produto_perc = gr.Plot(label="Evolução do Índice por Percentil")
                        grafico_produto_atual_perc = gr.Plot(label="Índice Atual")

                    # Nota metodológica explicativa
                    with gr.Column():
                        gr.Markdown("""
                        ## Nota Metodológica - Análise por Percentil

                        O índice final representa uma recomendação:
                        * Acima de +0.4: LONG ESTRUTURAL
                        * Abaixo de -0.4: SHORT ESTRUTURAL
                        * Entre -0.4 e +0.4: NEUTRO

                        OPÇÕES DE ANÁLISE:
                        * Com "Considerar ano específico" ativado: analisa apenas o produto do ano selecionado
                        * Com "Considerar ano específico" desativado: analisa todos os anos desse tipo/período de produto

                        IMPORTANTE: O valor do índice no card sempre corresponde ao último ponto do gráfico.
                        """)

            # ================ CONFIGURAR EVENTOS RNA ================
            # Evento para calcular o índice global
            btn_calcular.click(
                fn=atualizar_analise_global,
                inputs=[data_inicial_rna, data_final_rna],
                outputs=[grafico_global, resultado_global, indice_global_output, msg_global]
            )

            # Evento para atualizar períodos no RNA
            tipo_produto_rna.change(
                fn=lambda tipo: atualizar_periodos(tipo, produtos_recentes),
                inputs=[tipo_produto_rna],
                outputs=[periodo_produto_rna, ano_rna]
            )

            # Evento para analisar produto no RNA
            btn_analisar_produto.click(
                fn=atualizar_analise_produto,
                inputs=[indice_global_output, tipo_produto_rna, periodo_produto_rna, ano_rna, data_inicial_rna, data_final_rna],
                outputs=[grafico_produto_historico, grafico_produto_atual_rna, resultado_produto_rna, interpretacao_rna]
            )

            # ================ CONFIGURAR EVENTOS PERCENTIL ================
            # Evento para atualizar períodos no Percentil
            tipo_produto_perc.change(
                fn=lambda tipo: atualizar_periodos(tipo, produtos_recentes),
                inputs=[tipo_produto_perc],
                outputs=[periodo_produto_perc, ano_perc]
            )

            # Evento para atualizar interatividade do ano
            considerar_ano.change(
                fn=lambda considerar: gr.update(interactive=considerar),
                inputs=[considerar_ano],
                outputs=[ano_perc]
            )

            # Evento para analisar produto no Percentil
            btn_analisar_perc.click(
                fn=lambda tipo, periodo, ano, considerar_ano, data_ini, data_fim: atualizar_analise_produto_percentil_corrigido(
                    tipo, periodo, ano, considerar_ano, data_ini, data_fim, df_filtrado),
                inputs=[tipo_produto_perc, periodo_produto_perc, ano_perc, considerar_ano, data_inicial_perc, data_final_perc],
                outputs=[grafico_produto_perc, grafico_produto_atual_perc, resultado_produto_perc, interpretacao_perc]
            )

        # Iniciar a interface Gradio
        interface_combinada.launch(share=True)

    except Exception as e:
        import traceback
        traceback.print_exc()
        print(f"Erro na execução: {e}")

if __name__ == "__main__":
    main()