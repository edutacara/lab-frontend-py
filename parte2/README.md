# Parte 2 — Planejamento de Automação VPN IPSec: Fortigate ↔ Palo Alto

Plano de automação para configuração de uma VPN IPSec site-to-site entre um firewall Fortigate e um firewall Palo Alto, com validação de configuração e alertas.

---

## Parâmetros da VPN

| Parâmetro              | Fortigate              | Palo Alto              |
|------------------------|------------------------|------------------------|
| IP WAN                 | `100.64.0.1`           | `100.64.0.254`         |
| IP Mgmt (API)          | `192.168.50.10`        | `192.168.100.10`       |
| Rede LAN               | `192.168.10.0/24`      | `192.168.20.0/24`      |
| IP do Túnel            | `169.255.1.1/30`       | `169.255.1.2/30`       |
| Rede do Túnel          | `169.255.1.0/30`       | `169.255.1.0/30`       |

### Phase 1 (IKEv2)

| Parâmetro       | Valor         |
|-----------------|---------------|
| Versão IKE      | IKEv2         |
| Criptografia    | AES-256       |
| Hash            | SHA-256       |
| Grupo DH        | 14 (2048-bit) |
| Lifetime        | 86400 s       |
| Autenticação    | Pre-shared key|

### Phase 2 (IPSec)

| Parâmetro       | Valor         |
|-----------------|---------------|
| Protocolo       | ESP           |
| Criptografia    | AES-256       |
| Hash            | SHA-256       |
| PFS Group       | 14            |
| Lifetime        | 3600 s        |
| Proxy IDs       | any/any (0.0.0.0/0) — route-based |

### BGP (roteamento pelo túnel)

| Parâmetro        | Fortigate       | Palo Alto       |
|------------------|-----------------|-----------------|
| AS               | 65001           | 65002           |
| Router-ID        | 169.255.1.1     | 169.255.1.2     |
| Neighbor         | 169.255.1.2     | 169.255.1.1     |
| Neighbor AS      | 65002           | 65001           |
| Rede anunciada   | 192.168.10.0/24 | 192.168.20.0/24 |

---

## Algoritmos Proibidos — Criptografia Fraca

Os algoritmos abaixo **não devem ser configurados** por serem considerados inseguros ou deprecados. Scripts de automação devem validar e rejeitar configurações que os utilizem.

### Phase 1 (IKE)

| Parâmetro     | Não usar                              | Motivo                                      |
|---------------|---------------------------------------|---------------------------------------------|
| Versão IKE    | IKEv1                                 | Deprecado, vulnerável a ataques como MITM   |
| Criptografia  | DES, 3DES                             | DES = 56-bit, quebrado; 3DES vulnerável ao Sweet32 |
| Hash          | MD5, SHA-1                            | Colisões conhecidas, não recomendados pelo NIST |
| Grupo DH      | Group 1 (768-bit), Group 2 (1024-bit), Group 5 (1536-bit) | Tamanho de chave insuficiente contra ataques modernos |

### Phase 2 (IPSec)

| Parâmetro     | Não usar                              | Motivo                                      |
|---------------|---------------------------------------|---------------------------------------------|
| Criptografia  | DES, 3DES, NULL                       | DES/3DES fracos; NULL = sem criptografia    |
| Hash          | MD5, SHA-1                            | Colisões conhecidas                         |
| PFS           | Desabilitado                          | Sem PFS, comprometimento de uma chave expõe sessões anteriores |
| PFS Group     | Group 1, Group 2, Group 5             | Mesmos problemas dos grupos DH da Phase 1   |

### Referências
- [NIST SP 800-77 Rev. 1 — Guide to IPsec VPNs](https://csrc.nist.gov/publications/detail/sp/800-77/rev-1/final)
- [RFC 8221 — Cryptographic Algorithm Implementation Requirements for ESP and AH](https://www.rfc-editor.org/rfc/rfc8221)

---

## Ferramentas e APIs

### Fortigate
- **FortiOS REST API** — API nativa do FortiOS, autenticada via API token ou sessão. Endpoints no formato `https://<ip>/api/v2/cmdb/`.
- **Netmiko / Paramiko** — alternativa via SSH para dispositivos sem licença de API.

### Palo Alto
- **PAN-OS XML API** — API nativa do PAN-OS, autenticada via API key. Suporta operações `set`, `get`, `commit`.
- **pan-os-python** — biblioteca Python oficial da Palo Alto Networks que abstrai a XML API.
- **Panorama** — em ambientes com gerenciamento centralizado, pode ser usado no lugar da API direta.

---

## Passos de Automação

### 1. Validação de Pré-requisitos
- Verificar conectividade com ambos os firewalls via API
- Confirmar que as interfaces WAN estão ativas

### 2. Configuração no Fortigate (REST API)

```
1. Criar fase 1 (vpn ipsec phase1-interface)
   - Definir: interface WAN, peer IP, IKEv2, proposta, PSK

2. Criar fase 2 (vpn ipsec phase2-interface) — route-based
   - Proxy IDs: src 0.0.0.0/0 / dst 0.0.0.0/0 (any/any)
   - O roteamento é delegado ao BGP

3. Atribuir IP à interface do túnel (169.255.1.1/30)

4. Configurar BGP
   - AS local: 65001 / Neighbor: 169.255.1.2 AS 65002
   - Anunciar: 192.168.10.0/24

5. Criar política de firewall permitindo tráfego pelo túnel
```

### 3. Configuração no Palo Alto (XML API)

```
1. Criar IKE Crypto Profile
   - Definir: criptografia, hash, grupo DH, lifetime

2. Criar IPSec Crypto Profile
   - Definir: protocolo ESP, criptografia, hash, PFS, lifetime

3. Criar IKE Gateway
   - Definir: interface WAN, peer IP, IKEv2, PSK, crypto profile

4. Criar IPSec Tunnel — route-based
   - Sem proxy IDs configurados
   - Vincular: IKE gateway, IPSec crypto profile, tunnel interface

5. Atribuir IP à tunnel interface (169.255.1.2/30)

6. Configurar BGP
   - AS local: 65002 / Peer: 169.255.1.1 AS 65001
   - Redistribuir redes conectadas

7. Criar Security Policy permitindo tráfego entre zonas

8. Executar commit
```

### 4. Validação
- Verificar status do túnel em ambos os dispositivos
- Executar ping de teste através do túnel
- Gerar alertas em caso de falha

---

## Considerações Específicas

### Diferenças entre fabricantes

| Aspecto               | Fortigate                          | Palo Alto                          |
|-----------------------|------------------------------------|------------------------------------|
| Modelo de config      | Flat (config direto na CLI/API)    | Hierárquico (candidate + commit)   |
| API                   | REST (JSON)                        | XML (requer commit explícito)      |
| Túnel IP              | Configurado na fase 2              | Interface de túnel separada        |
| Rota                  | Automática via fase 2 ou estática  | Sempre estática via tunnel iface   |
| Validação de estado   | `diagnose vpn tunnel list`         | `show vpn ipsec-sa` via API op     |

### Desafios
- **Commit no Palo Alto:** toda configuração fica em estado pendente até o `commit`, exigindo tratamento de erros em duas etapas (configurar → confirmar).
- **Sincronismo de parâmetros:** Phase 1 e Phase 2 devem ser exatamente compatíveis entre os dois fabricantes. Diferenças de nomenclatura podem causar falhas silenciosas.
- **Autenticação:** o Fortigate usa API token por header; o Palo Alto usa API key por query parameter — requer tratamento separado no script.
- **Idempotência:** os scripts devem verificar se o objeto já existe antes de criar, para evitar erros em re-execuções.

---

## Validação de Configuração e Alertas

### Fortigate
```python
# Verificar status do túnel via API
GET /api/v2/monitor/vpn/ipsec
# Campo esperado: "proxyid_up" > 0
```

### Palo Alto
```xml
<!-- Verificar SAs ativas via operational command -->
<request><op><cmd>show vpn ipsec-sa</cmd></op></request>
<!-- Campo esperado: <state>init</state> ou <state>active</state> -->
```

### Estratégia de alertas
1. Após aplicar a configuração, aguardar 30 segundos para negociação IKE
2. Consultar status do túnel em ambos os dispositivos
3. Se `estado != ativo`:
   - Registrar o erro com timestamp
   - Exibir alerta com o dispositivo afetado e o estado retornado
   - Opcionalmente: notificar via e-mail ou webhook

---

## Troubleshooting de VPN

### Fortigate

#### Status geral do túnel
```
diagnose vpn tunnel list
diagnose vpn ike gateway list
diagnose vpn ipsec tunnel list
```

#### Debug IKE em tempo real
```bash
diagnose debug reset
diagnose debug application ike -1
diagnose debug enable
# Reproduzir o problema e depois desativar:
diagnose debug disable
diagnose debug reset
```

#### Verificar SAs ativas
```
get vpn ipsec tunnel summary
diagnose vpn ike gateway flush name VPN-PA-P1   # forçar renegociação
```

#### BGP
```
get router info bgp summary
get router info bgp neighbors 169.255.1.2
get router info routing-table bgp
```

#### Conectividade e roteamento
```
diagnose sniffer packet any "host 169.255.1.2" 4
execute ping-options source 169.255.1.1
execute ping 169.255.1.2
```

---

### Palo Alto

#### Status do túnel IPSec
```
show vpn ipsec-sa
show vpn ike-sa
show vpn flow name TUNNEL-FORTIGATE
```

#### Detalhes da negociação IKE
```
show vpn ike-sa gateway GW-FORTIGATE
show vpn ipsec-sa tunnel TUNNEL-FORTIGATE
```

#### Debug IKE/IPSec
```bash
debug ike global on debug
debug ike pcap on
# Reproduzir o problema e depois desativar:
debug ike global off
debug ike pcap off
less mp-log ikemgr.log
```

#### BGP
```
show routing protocol bgp summary
show routing protocol bgp peer 169.255.1.1
show routing route type bgp
```

#### Conectividade e roteamento
```
ping source 169.255.1.2 host 169.255.1.1
test routing fib-lookup virtual-router default ip 192.168.10.1
show interface tunnel.1
```

#### Logs do sistema
```
show log system direction equal forward
show log system subtype equal vpn
```

---

## Estrutura do Projeto

```
parte2/
├── README.md                     # Este documento
├── requirements.txt              # Dependências Python
└── scripts/
    ├── fortigate_vpn.py          # Configuração da VPN no Fortigate via REST API
    ├── fortigate_vpn.conf        # Configuração equivalente em CLI (FortiOS)
    ├── paloalto_vpn.py           # Configuração da VPN no Palo Alto via XML API
    ├── paloalto_vpn.conf         # Configuração equivalente em CLI (PAN-OS set commands)
    └── test_connectivity.py      # Teste de conectividade pelo túnel IPSec
```
