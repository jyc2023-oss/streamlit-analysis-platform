<template><div ref="root" class="echart-root" role="img" :aria-label="ariaLabel"></div></template>

<script setup>
import { onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { init, use } from 'echarts/core'
import { BarChart, LineChart } from 'echarts/charts'
import {
  AriaComponent, DataZoomComponent, GridComponent, LegendComponent,
  TitleComponent, ToolboxComponent, TooltipComponent,
} from 'echarts/components'
import { CanvasRenderer } from 'echarts/renderers'

use([
  AriaComponent, BarChart, CanvasRenderer, DataZoomComponent, GridComponent,
  LegendComponent, LineChart, TitleComponent, ToolboxComponent, TooltipComponent,
])

const props = defineProps({ option: { type: Object, required: true }, ariaLabel: { type: String, default: '数据图表' } })
const root = ref(null)
let chart = null
let observer = null

function render() { if (chart) chart.setOption(props.option, { notMerge: true, lazyUpdate: true }) }
onMounted(() => {
  chart = init(root.value, null, { renderer: 'canvas' })
  render()
  observer = new ResizeObserver(() => chart?.resize())
  observer.observe(root.value)
})
watch(() => props.option, render, { deep: true })
onBeforeUnmount(() => { observer?.disconnect(); chart?.dispose(); chart = null })
</script>

<style scoped>.echart-root{width:100%;height:100%;min-height:240px}</style>
