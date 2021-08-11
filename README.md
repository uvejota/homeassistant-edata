# homeassistant-edata
Esta integración para Home Assistant te permite seguir de un vistazo tus consumos y máximas potencias alcanzadas. Para ello, se apoya en proveedores de datos como datadis, por lo que necesitarás credenciales del mismo. 

## Instrucciones

1. Instala HACS en tu entorno de Home Assistant
2. Añade este repositorio (https://github.com/uvejota/homeassistant-edata) a los repositorios personalizados de HACS
3. Instala la integración. Por favor, considere que el estado actual de la integración es aún preliminar y puede lanzar fallos.
4. Configure la integración en su fichero de configuración de Home Assistant (e.g., `configuration.yaml`)
``` yaml
sensor:
  - platform: edata
    provider: datadis
    username: !secret my_username 
    password: !secret my_password 
    cups: !secret my_cups
```

A partir de este momento (tras reiniciar), le debería aparecer un nuevo sensor en Home Assistant llamado `sensor.edata_XXXX`, donde XXXX corresponde a los últimos cuatro caracteres de su CUPS. 

## Uso

Los estadísticos recopilados por esta integración se almacenan, de momento, como atributos. Puede visualizarlos mediante la siguiente tarjeta, sustituyendo `_XXXX` cuando sea necesario (dos veces):
``` yaml
type: markdown
content: >
  {% for attr in states.sensor.edata_XXXX.attributes %} {%- if not
  attr=="friendly_name" and not attr=="unit_of_measurement"  and not
  attr=="icon" -%} **{{attr}}**: {{state_attr("sensor.edata_XXXX", attr)}} {{-
  '\n' -}} {%- endif %} {%- endfor -%}
title: Informe
```

La tarjeta anterior mostrará un informe con los siguientes datos:

| Parámetro | Tipo | Unidad | Significado |
| ------------- | ------------- | ------------- | ------------- |
| cups | `string` | - | Identificador de su CUPS |
| `contract_p1_kW` | `float` | `kW` | Potencia contratada en P1 en el contrato vigente |
| `contract_p2_kW` | `float` | `kW` | Potencia contratada en P2 en el contrato vigente |
| `today_kWh` | `float` | `kWh` | Consumo total registrado durante el día de hoy |
| `today_p1_kWh` | `float` | `kWh` | Consumo en P1 registrado durante el día de hoy |
| `today_p2_kWh` | `float` | `kWh` | Consumo en P2 registrado durante el día de hoy |
| `today_p3_kWh` | `float` | `kWh` | Consumo en P3 registrado durante el día de hoy |
| `yesterday_kWh` | `float` | `kWh` | Consumo total registrado durante el día de ayer |
| `yesterday_p1_kWh` | `float` | `kWh` | Consumo en P1 registrado durante el día de ayer |
| `yesterday_p2_kWh` | `float` | `kWh` | Consumo en P2 registrado durante el día de ayer |
| `yesterday_p3_kWh` | `float` | `kWh` | Consumo en P3 registrado durante el día de ayer |
| `month_kWh` | `float` | `kWh` | Consumo total registrado durante el mes en curso |
| `month_days` | `float` | `d` | Días computados en el mes en curso |
| `month_daily_kWh` | `float` | `kWh` | Consumo medio diario registrado durante el mes en curso |
| `month_p1_kWh` | `float` | `kWh` | Consumo en P1 registrado durante el mes en curso |
| `month_p2_kWh` | `float` | `kWh` | Consumo en P2 registrado durante el mes en curso |
| `month_p3_kWh` | `float` | `kWh` | Consumo en P3 registrado durante el mes en curso |
| `last_month_kWh` | `float` | `kWh` | Consumo total registrado durante el mes pasado |
| `last_month_days_kWh` | `float` | `kWh` | Días computados en el mes pasado |
| `last_month_daily_kWh` | `float` | `kWh` | Consumo diario registrado durante el mes pasado |
| `last_month_p1_kWh` | `float` | `kWh` | Consumo en P1 registrado durante el mes pasado |
| `last_month_p2_kWh` | `float` | `kWh` | Consumo en P2 registrado durante el mes pasado |
| `last_month_p3_kWh` | `float` | `kWh` | Consumo en P3 registrado durante el mes pasado |
| `max_power_kW` | `float` | `kW` | Máxima potencia registrada en los últimos 12 meses |
| `max_power_date` | `date` | `%Y-%m-%d %H:%S` | Fecha correspondiente a la máxima potencia registrada en los últimos 12 meses |
| `max_power_mean_kW` | `float` | `kW` | Media de las potencias máximas registradas en los últimos 12 meses |
| `max_power_90perc_kW` | `float` | `kW` | Percentil 90 de las potencias máximas registradas en los últimos 12 meses |

## Configuración personalizada
En este momento, la integración permite la siguiente configuración
| Parámetro | Valores posibles | Recomendado |
| ------------- | ------------- | ------------- |
| `provider`  | `[datadis, edistribución]` | `datadis` |