import {
  LitElement,
  html,
} from "https://unpkg.com/lit-element@2.0.1/lit-element.js?module";
import "https://cdnjs.cloudflare.com/ajax/libs/apexcharts/3.45.1/apexcharts.min.js?module";

// Set program constants and definitions
const PROG_NAME = "edata-card";
const VALID_CHART_TEMPLATES = ["consumptions", "surplus", "maximeter", "costs", "consumption-summary"];
const DEF_CHART_TEMPLATE = "consumptions";
const VALID_AGGR_PERIODS = ["year", "month", "week", "day", "hour"];
const DEF_AGGR_PERIOD = "month";
const DEF_RECORDS_FOR_METHOD = {
  year: 3,
  month: 13,
  week: 4,
  day: 60,
  hour: 48,
};
const DEF_ROUND_DECIMALS = 1;
const DEF_ENERGY_UNIT = "kWh";
const DEF_POWER_UNIT = "kW";
const DEF_COST_UNIT = "€";
const LABELS_BY_LOCALE = {
  es: {
    p1: "Punta",
    p2: "Llano",
    p3: "Valle",
    p2_3: "Llano y Valle",
    surplus: "Retorno"
  },
};

// Set apexcharts defaults:
Apex.xaxis = {
  type: "datetime",
  labels: {
    datetimeUTC: false,
  },
};

Apex.chart = {
  toolbar: {
    show: false,
  },
  zoom: {
    enabled: false,
  },
  animations: {
    enabled: false,
  },
  background: "transparent",
};

Apex.yaxis = {
  labels: {
    formatter: (value) => {
      return value.toFixed(DEF_ROUND_DECIMALS);
    },
  },
};

Apex.dataLabels = {
  enabled: false,
};

Apex.tooltip = {
  enabled: true,
  intersect: false,
  shared: true,
  onDataHover: {
    highlightDataSeries: false,
  },
};

Apex.colors = ["#e54304", "#ff9e22", "#9ccc65"];

// EdataCard class
class EdataCard extends LitElement {
  constructor() {
    super();
    this._loaded = false;
  }

  static get properties() {
    return {
      hass: {},
      config: {},
      _left_title: "",
      _left_value: "",
      _left_unit: "",
      _right_title: "",
      _right_value: "",
      _right_unit: ""
    };
  }

  static getConfigElement() {
    // Create and return an editor element
    return document.createElement("edata-card-editor");
  }

  static getStubConfig() {
    return {
      entity: undefined,
      chart: "consumption",
      aggr: "month",
      records: 12,
      title: "edata",
    };
  }

  set hass(hass) {
    this._hass = hass;

    // Override defaults based on dark mode
    if (hass.themes.darkMode) {
      Apex.theme = {
        mode: "dark",
      };
    }
  }

  render() {
    return html`
      <ha-card>
        <div style="color: var(--secondary-text-color); font-size: 16px; font-weight: 500; overflow: hidden; white-space: nowrap; text-overflow: ellipsis; padding-left: 15px; padding-top: 15px; ">
          ${this._title}
        </div>

        <div style="position: relative; width: 100%; height: 100%; margin: 0 auto;">

        <div id="left" style="position: absolute; width: 20%; height: 20%; top: 0; left: 0; display: flex; align-items: top; justify-content: center; padding-top: 10px">
          <div id="left-box" style="padding-left: 10px; padding-top: 10px">
            <span style="font-size: 20px; font-weight: bold;">${this._left_value}</span><span style="font-size: 14px; color: var(--secondary-text-color);"> ${this._left_unit}</span>
            <br><span style="color: var(--secondary-text-color); font-size: 14px;">${this._left_title}</span>
          </div>
        </div>

        <div style="position: relative; width: 100%; height: 100%; margin: 0 auto">
          <div id="chart" style="display: flex; justify-content: center; align-items: center;"></div>
        </div>

        <div id="right" style="position: absolute; width: 20%; height: 20%; top: 0; right: 10px; display: flex; align-items: top; justify-content: center; padding-top: 10px">

        <div id="right-box" style="padding-right: 10px; padding-top: 10px; text-align: right">
          <span style="font-size: 20px; font-weight: bold;">${this._right_value}</span><span style="font-size: 14px; color: var(--secondary-text-color);"> ${this._right_unit}</span>
          <br><span style="color: var(--secondary-text-color); font-size: 14px;">${this._right_title}</span>
        </div>

        </div>
      </div>
      </ha-card>
    `;
  }

  setConfig(config) {
    if (!config.entity?.startsWith("sensor.edata")) {
      throw new Error("You need to define a valid entity (sensor.edata_XXXX)");
    }

    // extract scups
    this._scups = config.entity.split("_")[1];

    // config validation
    this._entity = config.entity;
    this._template = VALID_CHART_TEMPLATES.includes(config.chart)
      ? config.chart
      : DEF_CHART_TEMPLATE;
    this._aggr = VALID_AGGR_PERIODS.includes(config.aggr)
      ? config.aggr
      : DEF_AGGR_PERIOD;
    this._records = Number.isInteger(config.records)
      ? config.records
      : DEF_RECORDS_FOR_METHOD[this._aggr];
    this._title = config.title || PROG_NAME;

    this._colors = config.colors || Apex.colors;
    // store original config
    this._config = config;
  }

  connectedCallback() {
    super.connectedCallback();
    if (!this._loaded) {
      this.renderChart();
    }
  }

  updated(changedProps) {
    super.updated(changedProps);
    if (!this._loaded) {
      this.renderChart();
    }
  }

  async getConsumptionChartOptions() {

    const [p1, p2, p3] = this.normalizeX(
      await this._hass.callWS({
        type: "edata/ws/consumptions",
        scups: this._scups,
        aggr: this._aggr,
        tariff: "p1",
        records: this._records,
      }), await this._hass.callWS({
        type: "edata/ws/consumptions",
        scups: this._scups,
        aggr: this._aggr,
        tariff: "p2",
        records: this._records,
      }), await this._hass.callWS({
        type: "edata/ws/consumptions",
        scups: this._scups,
        aggr: this._aggr,
        tariff: "p3",
        records: this._records,
      })
    )

    var config = {
      chart: {
        stacked: true,
        id: "chart",
        type: "bar",
      },
      colors: this._colors,
      yaxis: {
        title: {
          text: DEF_ENERGY_UNIT,
        },
      },
      series: [
        {
          name: LABELS_BY_LOCALE["es"]["p1"],
          data: p1,
        },
        {
          name: LABELS_BY_LOCALE["es"]["p2"],
          data: p2,
        },
        {
          name: LABELS_BY_LOCALE["es"]["p3"],
          data: p3,
        },
      ],
    };

    if (this._aggr == "year") {
      config["xaxis"] = {
        tickAmount: "dataPoints",
        labels: {
          datetimeUTC: false,
          formatter: function (val) {
            return new Date(val).getFullYear().toString();
          }
        }
      }
    }

    return config
  }

  async getSurplusChartOptions() {
    var config = {
      chart: {
        stacked: true,
        type: "bar",
      },
      colors: this._colors,
      yaxis: {
        title: {
          text: DEF_ENERGY_UNIT,
        },
      },
      series: [
        {
          name: LABELS_BY_LOCALE["es"]["surplus"],
          data: await this._hass.callWS({
            type: "edata/ws/surplus",
            scups: this._scups,
            aggr: this._aggr,
            records: this._records,
          }),
        }
      ],
    };

    if (this._aggr == "year") {
      config["xaxis"] = {
        tickAmount: "dataPoints",
        labels: {
          datetimeUTC: false,
          formatter: function (val) {
            return new Date(val).getFullYear().toString();
          }
        }
      }
    }

    return config
  }

  async getCostsChartOptions() {
    const [p1, p2, p3] = this.normalizeX(
      await this._hass.callWS({
        type: "edata/ws/costs",
        scups: this._scups,
        aggr: this._aggr,
        tariff: "p1",
        records: this._records,
      }), await this._hass.callWS({
        type: "edata/ws/costs",
        scups: this._scups,
        aggr: this._aggr,
        tariff: "p2",
        records: this._records,
      }), await this._hass.callWS({
        type: "edata/ws/costs",
        scups: this._scups,
        aggr: this._aggr,
        tariff: "p3",
        records: this._records,
      })
    )

    var config = {
      chart: {
        stacked: true,
        type: "bar",
      },
      colors: this._colors,
      yaxis: {
        title: {
          text: DEF_COST_UNIT,
        },
      },
      series: [
        {
          name: LABELS_BY_LOCALE["es"]["p1"],
          data: p1,
        },
        {
          name: LABELS_BY_LOCALE["es"]["p2"],
          data: p2,
        },
        {
          name: LABELS_BY_LOCALE["es"]["p3"],
          data: p3,
        },
      ],
    };

    if (this._aggr == "year") {
      config["xaxis"] = {
        tickAmount: "dataPoints",
        labels: {
          datetimeUTC: false,
          formatter: function (val) {
            return new Date(val).getFullYear().toString();
          }
        }
      }
    }

    return config
  }

  async getMaximeterChartOptions() {
    return {
      chart: {
        id: "chart",
        type: "scatter",
      },
      colors: this._colors,
      yaxis: {
        title: {
          text: DEF_POWER_UNIT,
        },
      },
      series: [
        {
          name: LABELS_BY_LOCALE["es"]["p1"],
          data: await this._hass.callWS({
            type: "edata/ws/maximeter",
            scups: this._scups,
            tariff: "p1",
          }),
        },
        {
          name: LABELS_BY_LOCALE["es"]["p2_3"],
          data: await this._hass.callWS({
            type: "edata/ws/maximeter",
            scups: this._scups,
            tariff: "p2",
          }),
        },
      ],
    };
  }

  async getConsumptionSummaryOptions() {

    const [p1, p2, p3] = this.normalizeX(
      await this._hass.callWS({
        type: "edata/ws/consumptions",
        scups: this._scups,
        aggr: this._aggr,
        tariff: "p1",
        records: this._records,
      }), await this._hass.callWS({
        type: "edata/ws/consumptions",
        scups: this._scups,
        aggr: this._aggr,
        tariff: "p2",
        records: this._records,
      }), await this._hass.callWS({
        type: "edata/ws/consumptions",
        scups: this._scups,
        aggr: this._aggr,
        tariff: "p3",
        records: this._records,
      })
    )

    const item_p1 = p1.slice(-this._records)[0]
    const item_p2 = p2.slice(-this._records)[0]
    const item_p3 = p3.slice(-this._records)[0]

    const date = new Date(item_p1[0])
    this._left_value = Math.round(item_p1[1] + item_p2[1] + item_p3[1])
    this._left_unit = DEF_ENERGY_UNIT
    this._left_title = "Total"
    this._right_value = date.getDate() + "/" + date.getMonth()
    this._right_unit = ""
    this._right_title = "Fecha"
    if (this._aggr === "day") {
      this._right_value = date.getDate() + "/" + date.getMonth()
    } else if (this._aggr === "month"){
      this._right_value = date.getMonth() + "/" + date.getFullYear()
    } else if (this._aggr === "year"){
      this._right_value = date.getFullYear()
    } else if (this._aggr === "hour"){
      this._right_value = date.getDate() + "/" + date.getMonth() + " " + date.getHours() + "h"
    } else {
      this._right_title = ""
    }

    var config = {
      chart: {
        id: "chart",
        type: "pie",
        width: 300,
      },
      colors: this._colors,
      series: [item_p1[1] , item_p2[1] , item_p3[1] ],
      labels: [LABELS_BY_LOCALE["es"]["p1"], LABELS_BY_LOCALE["es"]["p2"], LABELS_BY_LOCALE["es"]["p3"]],
      legend: {
        position: "bottom"
      },
    };

    if (this._aggr == "year") {
      config["xaxis"] = {
        tickAmount: "dataPoints",
        labels: {
          datetimeUTC: false,
          formatter: function (val) {
            return new Date(val).getFullYear().toString();
          }
        }
      }
    }

    return config
  }

  normalizeX(list1, list2, list3) {
      const allX = new Set();

      // Recopilamos todos los valores únicos de x de las tres listas
      list1.forEach(([x, _]) => allX.add(x));
      list2.forEach(([x, _]) => allX.add(x));
      list3.forEach(([x, _]) => allX.add(x));

      // Convertimos el set a array y lo ordenamos
      const sortedX = Array.from(allX).sort((a, b) => a - b);

      const mergeList = (list) => {
          const map = new Map(list);
          return sortedX.map(x => [x, map.get(x) || 0]);
      };

      const newList1 = mergeList(list1);
      const newList2 = mergeList(list2);
      const newList3 = mergeList(list3);

      return [newList1, newList2, newList3];
  }

  async renderChart() {
    await this.updateComplete;

    if (!this._loaded && !this._chart) {
      this._loaded = true;
      var chartOptions;

      switch (this._template) {
        case "consumptions":
          chartOptions = await this.getConsumptionChartOptions();
          break;
        case "surplus":
          chartOptions = await this.getSurplusChartOptions();
          break;
        case "costs":
          chartOptions = await this.getCostsChartOptions();
          break;
        case "maximeter":
          chartOptions = await this.getMaximeterChartOptions();
          break;
        case "consumption-summary":
          chartOptions = await this.getConsumptionSummaryOptions();
          break;
      }

      this.render();
      this._chart = new ApexCharts(
        this.shadowRoot.querySelector("#chart"),
        chartOptions
      );
      this._chart.render();
    }
  }

  getCardSize() {
    return 3;
  }
}

window.customCards = window.customCards || [];
window.customCards.push({
  type: "edata-card",
  name: "edata",
  preview: true,
  description: "Visualize edata's data!",
  documentationURL: "https://github.com/uvejota/homeassistant-edata",
});

customElements.define("edata-card", EdataCard);


class EdataCardEditor extends LitElement {


  static get properties() {
    return {
      hass: {},
      _config: {},
    };
  }

  _valueChanged(ev) {
    if (!this._config || !this.hass) {
      return;
    }
    const _config = Object.assign({}, this._config);
    _config.title = ev.detail.value.title;
    _config.entity = ev.detail.value.entity;
    _config.chart = ev.detail.value.chart;
    _config.aggr = ev.detail.value.aggr;
    _config.records = ev.detail.value.records;

    this._config = _config;

    const event = new CustomEvent("config-changed", {
      detail: { config: _config },
      bubbles: true,
      composed: true,
    });
    this.dispatchEvent(event);
  }


  setConfig(config) {
    this._config = config;
  }

  render() {
    if (!this.hass || !this._config) {
      return html``;
    }

    return html`<ha-form
      .hass=${this.hass}
      .data=${this._config}
      .schema=${[
      { name: "title", selector: { text: {} } },
      { name: "entity", selector: { select: { options: Object.keys(this.hass.states).filter(entity => entity.startsWith('sensor.edata_')), mode: "dropdown" } } },
      { name: "chart", selector: { select: { options: VALID_CHART_TEMPLATES, mode: "dropdown"  } } },
      { name: "aggr", selector: { select: { options: VALID_AGGR_PERIODS, mode: "dropdown" } } },
      { name: "records", selector: { number: { min: 1, max: 365  } } },
      ]}
      .computeLabel=${this._computeLabel}
      @value-changed=${this._valueChanged}
      ></ha-form>
    `;
  }

  _computeLabel(schema) {
    var labelMap = {
      title: "Título",
      entity: "Entidad",
      chart: "Gráfica",
      aggr: "Agregación",
      records: "Registros",
    }
    return labelMap[schema.name];
  }


}

customElements.define("edata-card-editor", EdataCardEditor);
