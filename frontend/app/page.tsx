'use client'
import { useState, useCallback, useRef } from 'react'
import { Upload, Download, RotateCcw, AlertCircle, Wrench, Flag, ArrowLeftRight, BarChart3, History, KeyRound } from 'lucide-react'
import Dashboard from '@/components/Dashboard'
import PendenciasManual from '@/components/PendenciasManual'
import Historico from '@/components/Historico'
import Comparativo from '@/components/Comparativo'

type Tab = 'erros' | 'fixes' | 'flags' | 'diff' | 'dashboard' | 'pendencias' | 'historico' | 'comparativo'

export default function Home() {
  const [dragging, setDragging]     = useState(false)
  const [loading,  setLoading]      = useState(false)
  const [progress, setProgress]     = useState(0)
  const [procId,   setProcId]       = useState<number | null>(null)
  const [resultado, setResultado]   = useState<any>(null)
  const [activeTab, setActiveTab]   = useState<Tab>('erros')
  const [filtro,   setFiltro]       = useState('todos')
  const [busca,    setBusca]        = useState('')
  const fileRef = useRef<HTMLInputElement>(null)

  const processar = useCallback(async (file: File) => {
    setLoading(true); setProgress(10); setResultado(null); setProcId(null)
    try {
      const fd = new FormData(); fd.append('file', file)
      setProgress(30)
      const r1 = await fetch('/api/processar', { method: 'POST', body: fd })
      if (!r1.ok) throw new Error(await r1.text())
      const j1 = await r1.json()
      setProgress(70)
      const r2 = await fetch(`/api/resultado/${j1.id}`)
      if (!r2.ok) throw new Error('Erro ao buscar resultado')
      const data = await r2.json()
      setProgress(100)
      setProcId(j1.id); setResultado(data); setActiveTab('erros')
    } catch (e: any) {
      alert('Erro: ' + e.message)
    } finally {
      setLoading(false); setTimeout(() => setProgress(0), 500)
    }
  }, [])

  const onDrop = useCallback((e: React.DragEvent) => {
    e.preventDefault(); setDragging(false)
    const f = e.dataTransfer.files[0]
    if (f) processar(f)
  }, [processar])

  const reset = () => { setResultado(null); setProcId(null); setProgress(0); setActiveTab('erros') }

  // ── Filtrar itens ─────────────────────────────────────────────
  const filtrar = (items: any[]) => {
    let out = items
    if (filtro !== 'todos') out = out.filter((x: any) => (x.reg || '')[0] === filtro)
    if (busca) {
      const b = busca.toLowerCase()
      out = out.filter((x: any) =>
        (x.reg||'').toLowerCase().includes(b) ||
        (x.desc||'').toLowerCase().includes(b) ||
        String(x.linha||'').includes(b) ||
        (x.orig||'').toLowerCase().includes(b) ||
        (x.novo||'').toLowerCase().includes(b)
      )
    }
    return out
  }

  const TABS = resultado ? [
    { id: 'erros',      label: 'Erros',      icon: AlertCircle, count: resultado.erros.length,       color: 'text-red-400' },
    { id: 'fixes',      label: 'Corrigidos', icon: Wrench,      count: resultado.fixes.length,       color: 'text-purple-400' },
    { id: 'flags',      label: 'Flags',      icon: Flag,        count: resultado.flags.length,       color: 'text-amber-400' },
    { id: 'diff',       label: 'Diff',       icon: ArrowLeftRight, count: resultado.fixes.length,   color: 'text-blue-400' },
    { id: 'pendencias', label: 'Pendências',  icon: AlertCircle, count: resultado.erros.filter((e:any)=>e.desc?.includes('CHV_NFE')).length || null, color: 'text-red-400' },
    { id: 'dashboard',  label: 'Dashboard',  icon: BarChart3,   count: null,                         color: 'text-green-400' },
    { id: 'historico',  label: 'Histórico',  icon: History,     count: null,                         color: 'text-blue-400' },
    { id: 'comparativo',label: 'Comparativo',icon: BarChart3,   count: null,                         color: 'text-purple-400' },
  ] : [
    { id: 'historico',  label: 'Histórico',  icon: History,     count: null, color: 'text-blue-400' },
  ]

  const blocos = resultado ? [...new Set(
    (activeTab === 'erros' ? resultado.erros :
     activeTab === 'fixes' ? resultado.fixes :
     activeTab === 'flags' ? resultado.flags :
     resultado.fixes).map((x: any) => (x.reg||'')[0])
  )].filter(Boolean).sort() : []

  return (
    <div className="flex flex-col min-h-screen bg-bg">
      {/* Header */}
      <header className="flex items-center justify-between px-8 h-14 bg-bg2 border-b border-border">
        <div className="flex items-center gap-3">
          <div className="w-8 h-8 rounded-md bg-green flex items-center justify-center font-mono text-xs font-medium text-black">EFD</div>
          <div>
            <div className="text-sm font-medium">
              Autocorretor SPED {resultado?.tipo === 'contrib' ? 'EFD-Contribuições (PIS/COFINS)' : 'EFD ICMS/IPI'}
            </div>
            <div className="text-xs font-mono text-gray-500">
              {resultado?.tipo === 'contrib' ? 'v1 · 182 registros · PIS/COFINS' : 'v9 · descritor.xml oficial PVA'}
            </div>
          </div>
          {resultado?.tipo && (
            <span className={`text-xs font-mono px-2 py-0.5 rounded ${resultado.tipo === 'contrib' ? 'bg-blue-900/30 text-blue-400' : 'bg-green/10 text-green'}`}>
              {resultado.tipo === 'contrib' ? 'PIS/COFINS' : 'ICMS/IPI'}
            </span>
          )}
        </div>
        {resultado && (
          <div className="flex items-center gap-2 text-xs font-mono text-gray-500">
            <span className="px-2 py-1 rounded bg-bg3 border border-border">{resultado.uf}</span>
            <span className="px-2 py-1 rounded bg-bg3 border border-border">{resultado.dt_ini} – {resultado.dt_fin}</span>
            <span className="px-2 py-1 rounded bg-bg3 border border-border">v{resultado.versao}</span>
          </div>
        )}
      </header>

      <div className="flex flex-1 overflow-hidden">
        {/* Sidebar */}
        <aside className="w-72 bg-bg2 border-r border-border flex flex-col p-5 gap-4 overflow-y-auto">
          {/* Upload */}
          <div>
            <div className="text-xs font-semibold uppercase tracking-widest text-gray-500 mb-2">Arquivo SPED</div>
            <div
              className={`border rounded-xl p-6 text-center cursor-pointer transition-all
                ${dragging ? 'border-green bg-green/5' : 'border-border2 bg-bg3 hover:border-green hover:bg-green/5'}
                ${loading ? 'opacity-50 pointer-events-none' : ''}`}
              onDragOver={e => { e.preventDefault(); setDragging(true) }}
              onDragLeave={() => setDragging(false)}
              onDrop={onDrop}
              onClick={() => fileRef.current?.click()}
            >
              <Upload className="w-7 h-7 mx-auto mb-2 opacity-30" />
              <p className="text-sm text-gray-400 mb-1">Arraste o .txt aqui</p>
              <span className="text-xs font-mono text-gray-600">ISO-8859-1 · ICMS/IPI ou Contribuições</span>
              <input ref={fileRef} type="file" accept=".txt" className="hidden"
                onChange={e => { if (e.target.files?.[0]) processar(e.target.files[0]) }} />
            </div>
          </div>

          {/* Progresso */}
          {loading && (
            <div>
              <div className="flex justify-between text-xs font-mono text-gray-500 mb-1">
                <span>Processando...</span><span>{progress}%</span>
              </div>
              <div className="h-0.5 bg-border rounded overflow-hidden">
                <div className="h-full bg-green transition-all duration-300" style={{width: `${progress}%`}} />
              </div>
            </div>
          )}

          {/* Métricas */}
          {resultado && (
            <div>
              <div className="text-xs font-semibold uppercase tracking-widest text-gray-500 mb-2">Resultado</div>
              <div className="grid grid-cols-2 gap-2">
                {[
                  { label: 'Registros', val: resultado.sumario?.total_regs?.toLocaleString('pt-BR'), color: 'text-blue-400' },
                  { label: 'Linhas',    val: resultado.sumario?.total_linhas?.toLocaleString('pt-BR'), color: 'text-blue-400' },
                  { label: 'Erros',     val: resultado.erros.length, color: 'text-red-400' },
                  { label: 'Flags',     val: resultado.flags.length, color: 'text-amber-400' },
                  { label: 'Corrigidos',val: resultado.fixes.length, color: 'text-purple-400' },
                  { label: 'Válidos',   val: Math.max(0,(resultado.sumario?.total_regs||0)-resultado.erros.length-resultado.flags.length).toLocaleString('pt-BR'), color: 'text-green' },
                ].map(m => (
                  <div key={m.label} className="bg-bg3 border border-border rounded-lg p-2.5">
                    <div className={`text-xl font-semibold font-mono leading-none mb-0.5 ${m.color}`}>{m.val}</div>
                    <div className="text-xs uppercase tracking-wide text-gray-600">{m.label}</div>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Ações */}
          {resultado && procId && (
            <div className="flex flex-col gap-2">
              <div className="text-xs font-semibold uppercase tracking-widest text-gray-500 mb-1">Exportar</div>
              <a href={`/api/download/${procId}`}
                className="flex items-center justify-center gap-2 px-3 py-2 rounded-lg bg-green text-black font-medium text-sm hover:bg-emerald-400 transition-colors">
                <Download className="w-4 h-4" /> Baixar SPED corrigido
              </a>
              <button onClick={reset}
                className="flex items-center justify-center gap-2 px-3 py-2 rounded-lg border border-border2 text-sm hover:bg-bg3 transition-colors">
                <RotateCcw className="w-4 h-4" /> Novo arquivo
              </button>
            </div>
          )}
        </aside>

        {/* Conteúdo principal */}
        <main className="flex-1 flex flex-col overflow-hidden">
          {/* Tabs */}
          <div className="flex bg-bg2 border-b border-border px-6 overflow-x-auto">
            {TABS.map(t => (
              <button key={t.id} onClick={() => { setActiveTab(t.id as Tab); setFiltro('todos'); setBusca('') }}
                className={`flex items-center gap-2 px-4 py-3.5 text-xs font-medium border-b-2 transition-colors whitespace-nowrap
                  ${activeTab === t.id
                    ? 'border-green text-white'
                    : 'border-transparent text-gray-500 hover:text-gray-300'}`}>
                <t.icon className="w-3.5 h-3.5" />
                {t.label}
                {t.count !== null && (
                  <span className={`text-xs font-mono px-1.5 py-0.5 rounded bg-bg3
                    ${t.count > 0 ? t.color.replace('text-','bg-').replace('-400','') + '/20 ' + t.color : 'text-gray-600'}`}>
                    {t.count}
                  </span>
                )}
              </button>
            ))}
          </div>

          {/* Painéis */}
          <div className="flex-1 overflow-y-auto p-6">
            {!resultado && activeTab !== 'historico' && (
              <div className="flex flex-col items-center justify-center h-full gap-4 text-gray-600">
                <div className="text-5xl opacity-10">⌂</div>
                <p className="text-sm">Carregue um arquivo SPED (ICMS/IPI ou Contribuições)</p>
                <p className="text-xs font-mono">Detecção automática do tipo de escrituração</p>
              </div>
            )}

            {activeTab === 'historico' && <Historico onSelect={setProcId} />}
            {activeTab === 'comparativo' && resultado && <Comparativo cnpj={resultado.cnpj} />}
            {activeTab === 'pendencias' && resultado && procId && (
              <PendenciasManual procId={procId} tipo={resultado.tipo || 'icms'} onAlterado={() => {
                fetch(`/api/resultado/${procId}`).then(r=>r.json()).then(setResultado)
              }} />
            )}
            {activeTab === 'dashboard' && resultado && <Dashboard sumario={resultado.sumario} tipo={resultado.tipo || 'icms'} />}

            {resultado && ['erros','fixes','flags','diff'].includes(activeTab) && (
              <>
                {/* Filtros */}
                <div className="flex gap-2 mb-4 flex-wrap items-center">
                  <input value={busca} onChange={e => setBusca(e.target.value)}
                    placeholder="buscar reg., descrição, linha..."
                    className="flex-1 min-w-32 px-3 py-1.5 rounded-lg border border-border2 bg-bg3 text-xs font-mono text-white placeholder-gray-600 focus:outline-none focus:border-green" />
                  {['todos', ...blocos].map(b => (
                    <button key={b} onClick={() => setFiltro(b)}
                      className={`px-3 py-1 rounded-full text-xs font-mono border transition-colors
                        ${filtro === b ? 'bg-white text-bg border-white' : 'border-border2 text-gray-400 hover:border-gray-400'}`}>
                      {b}
                    </button>
                  ))}
                </div>

                {/* Cards */}
                <div className="space-y-2">
                  {filtrar(
                    activeTab === 'erros' ? resultado.erros :
                    activeTab === 'fixes' ? resultado.fixes :
                    activeTab === 'flags' ? resultado.flags :
                    resultado.fixes
                  ).map((item: any, idx: number) => (
                    <div key={idx} className="bg-bg2 border border-border hover:border-border2 rounded-lg p-3 flex gap-3">
                      <div className={`w-2 h-2 rounded-full flex-shrink-0 mt-1.5
                        ${activeTab==='erros' ? 'bg-red-400 shadow-[0_0_5px_#ff4757]' :
                          activeTab==='fixes' ? 'bg-purple-400' :
                          activeTab==='flags' ? 'bg-amber-400' : 'bg-green'}`} />
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center gap-2 mb-1 flex-wrap">
                          <span className="font-mono text-xs font-medium">{item.reg}</span>
                          <span className={`text-xs px-1.5 py-0.5 rounded font-mono
                            ${activeTab==='erros' ? 'bg-red-900/30 text-red-400' :
                              activeTab==='fixes' ? 'bg-purple-900/30 text-purple-400' :
                              activeTab==='flags' ? 'bg-amber-900/30 text-amber-400' : 'bg-green/10 text-green'}`}>
                            {activeTab==='erros'?'erro crítico':activeTab==='fixes'?'corrigido':activeTab==='flags'?'flag manual':'diff'}
                          </span>
                          {item.linha ? <span className="text-xs font-mono text-gray-600">linha {item.linha}</span> : null}
                        </div>
                        <div className="text-xs text-gray-300 mb-1">{item.desc}</div>
                        {(item.orig || item.novo) && (
                          <div className="flex gap-2 items-center text-xs font-mono mt-1 flex-wrap">
                            <span className="text-red-400 line-through">{item.orig}</span>
                            <span className="text-gray-600">→</span>
                            <span className="text-green">{item.novo}</span>
                          </div>
                        )}
                        {item.hint && <div className="text-xs text-gray-600 mt-1 pl-2 border-l-2 border-border2 italic">{item.hint}</div>}
                      </div>
                    </div>
                  ))}
                  {filtrar(
                    activeTab === 'erros' ? resultado.erros :
                    activeTab === 'fixes' ? resultado.fixes :
                    activeTab === 'flags' ? resultado.flags :
                    resultado.fixes
                  ).length === 0 && (
                    <div className="text-center py-12 text-gray-600 text-sm">
                      {activeTab === 'erros' ? '✓ Nenhum erro crítico' : 'Nenhum item encontrado'}
                    </div>
                  )}
                </div>
              </>
            )}
          </div>
        </main>
      </div>
    </div>
  )
}
