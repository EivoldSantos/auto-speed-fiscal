'use client'
import { useEffect, useState, useCallback } from 'react'
import { KeyRound, Trash2, Save, AlertCircle, CheckCircle, ChevronDown } from 'lucide-react'

interface Pendencia {
  tipo: 'chv_nfe' | 'e116' | 'e250' | 'm205_cod_rec' | 'm605_cod_rec'
  reg: string
  linha: number
  num_doc?: string
  dt_doc?: string
  cod_mod?: string
  raw: string
  descricao: string
  cod_rec_atual?: string
  cod_rec_invalido?: boolean
  cod_sugerido?: string
  cod_sugerido_st?: string
  validos_uf?: string[]
  uf?: string
  mes_ref_atual?: string
  mes_ref_esperado?: string
}

interface PendenciasResponse {
  pendencias: Pendencia[]
  total: number
  uf?: string
  cod_sugerido?: string
  validos_uf?: string[]
  tipo_sped?: string
}

interface Props {
  procId: number
  tipo?: string
  onAlterado?: () => void
}


export default function PendenciasManual({ procId, tipo = 'icms', onAlterado }: Props) {
  const [pendencias, setPendencias] = useState<Pendencia[]>([])
  const [loading, setLoading]       = useState(true)
  const [chaves, setChaves]         = useState<Record<number, string>>({})
  const [codRec, setCodRec]         = useState('')
  const [validosUF, setValidosUF]   = useState<string[]>([])
  const [codSugerido, setCodSugerido] = useState('')
  const [saving, setSaving]         = useState<Record<string, boolean>>({})
  const [ok, setOk]                 = useState<Record<string, boolean>>({})
  const [erro, setErro]             = useState<Record<string, string>>({})

  const carregar = useCallback(async () => {
    setLoading(true)
    try {
      const r = await fetch(`/api/pendencias/${procId}`)
      const d = await r.json()
      setPendencias(d.pendencias || [])
      const validList: string[] = d.validos_uf || []
      setValidosUF(validList)
      const sugerido = d.cod_sugerido || ''
      setCodSugerido(sugerido)
      // Pré-selecionar: sugerido > atual > primeiro válido
      const e116 = (d.pendencias || []).find((p: Pendencia) => p.tipo === 'e116')
      const atual = e116?.cod_rec_atual || ''
      if (sugerido) setCodRec(sugerido)
      else if (atual && validList.includes(atual)) setCodRec(atual)
      else if (validList.length > 0) setCodRec(validList[0])
    } finally { setLoading(false) }
  }, [procId])

  useEffect(() => { carregar() }, [carregar])

  const salvarChave = async (linha: number, acao: 'inserir' | 'excluir') => {
    const key = `chv_${linha}`
    setSaving(s => ({ ...s, [key]: true }))
    setErro(e => ({ ...e, [key]: '' }))
    try {
      const r = await fetch(`/api/editar/chave/${procId}?linha=${linha}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ chave: acao === 'excluir' ? '' : (chaves[linha] || '') })
      })
      if (!r.ok) {
        const d = await r.json()
        throw new Error(d.detail || 'Erro ao salvar')
      }
      setOk(o => ({ ...o, [key]: true }))
      setTimeout(() => { setOk(o => ({ ...o, [key]: false })); carregar(); onAlterado?.() }, 1500)
    } catch (e: any) {
      setErro(er => ({ ...er, [key]: e.message }))
    } finally {
      setSaving(s => ({ ...s, [key]: false }))
    }
  }

  const salvarCodRec = async () => {
    const key = 'cod_rec'
    setSaving(s => ({ ...s, [key]: true }))
    setErro(e => ({ ...e, [key]: '' }))
    try {
      const r = await fetch(`/api/editar/cod_rec/${procId}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ cod_rec: codRec, linha_e116: 0 })
      })
      if (!r.ok) {
        const d = await r.json()
        throw new Error(d.detail || 'Erro ao salvar')
      }
      const d = await r.json()
      setOk(o => ({ ...o, [key]: true }))
      setTimeout(() => { setOk(o => ({ ...o, [key]: false })); carregar(); onAlterado?.() }, 1500)
    } catch (e: any) {
      setErro(er => ({ ...er, [key]: e.message }))
    } finally {
      setSaving(s => ({ ...s, [key]: false }))
    }
  }

  if (loading) return (
    <div className="text-gray-500 text-sm p-4">Verificando pendências...</div>
  )

  const chvPendencias  = pendencias.filter(p => p.tipo === 'chv_nfe')
  const e116Pendencias = pendencias.filter(p => p.tipo === 'e116')
  const contribPendencias = pendencias.filter(p => p.tipo === 'm205_cod_rec' || p.tipo === 'm605_cod_rec')

  if (pendencias.length === 0) return (
    <div className="flex flex-col items-center justify-center py-12 gap-3 text-gray-600">
      <CheckCircle className="w-10 h-10 text-green opacity-60" />
      <p className="text-sm text-green">Nenhuma pendência manual encontrada</p>
    </div>
  )

  return (
    <div className="space-y-6">
      <div className="text-xs uppercase tracking-widest text-gray-500">
        {pendencias.length} pendência{pendencias.length !== 1 ? 's' : ''} requerem intervenção manual
      </div>

      {/* ── Bloco E116 ── */}
      {e116Pendencias.length > 0 && (
        <div className="bg-bg2 border border-border rounded-xl overflow-hidden">
          <div className="flex items-center gap-2 px-4 py-3 border-b border-border bg-bg3">
            <AlertCircle className="w-4 h-4 text-amber-400" />
            <span className="text-sm font-medium">E116 — Código de Receita & Mês de Referência</span>
            <span className="ml-auto text-xs font-mono px-2 py-0.5 rounded bg-amber-900/30 text-amber-400">
              {e116Pendencias.length} registro{e116Pendencias.length !== 1 ? 's' : ''}
            </span>
          </div>

          <div className="p-4 space-y-4">
            {/* Info automática MES_REF */}
            {e116Pendencias[0]?.mes_ref_esperado && (
              <div className="flex items-start gap-2 p-3 rounded-lg bg-green/5 border border-green/20">
                <CheckCircle className="w-4 h-4 text-green mt-0.5 flex-shrink-0" />
                <div className="text-xs text-gray-300">
                  <span className="text-green font-medium">MES_REF corrigido automaticamente</span>
                  {' '}para{' '}
                  <span className="font-mono text-white">{e116Pendencias[0].mes_ref_esperado}</span>
                  {' '}(período do registro 0000). Nenhuma ação necessária.
                </div>
              </div>
            )}

            {/* COD_REC dropdown */}
            <div>
              {codSugerido && codRec === codSugerido && (
                <div className="flex items-center gap-2 mb-2 px-2 py-1 rounded bg-green/10 border border-green/20 w-fit">
                  <CheckCircle className="w-3.5 h-3.5 text-green" />
                  <span className="text-xs text-green font-mono">
                    Código <strong>{codSugerido}</strong> detectado automaticamente para esta UF
                  </span>
                </div>
              )}
              <label className="text-xs text-gray-400 mb-2 block">
                COD_REC — aplicado a <strong className="text-white">{e116Pendencias.length}</strong> registro(s) E116
              </label>
              <div className="flex gap-2 items-start flex-wrap">
                <div className="relative flex-1 min-w-48">
                  <select
                    value={codRec}
                    onChange={e => setCodRec(e.target.value)}
                    className="w-full appearance-none bg-bg3 border border-border2 rounded-lg px-3 py-2 text-sm font-mono text-white focus:outline-none focus:border-green pr-8"
                  >
                    {validosUF.length > 0 ? validosUF.map(c => (
                      <option key={c} value={c}>
                        {c}{c === codSugerido ? ' ✓ (recomendado)' : ''}
                      </option>
                    )) : (
                      <option value={codRec}>{codRec || '— selecione —'}</option>
                    )}
                  </select>
                  <ChevronDown className="absolute right-2 top-2.5 w-4 h-4 text-gray-500 pointer-events-none" />
                </div>
                <button
                  onClick={salvarCodRec}
                  disabled={saving['cod_rec']}
                  className="flex items-center gap-2 px-4 py-2 rounded-lg bg-amber-500/20 border border-amber-500/40 text-amber-300 text-sm hover:bg-amber-500/30 transition-colors disabled:opacity-50"
                >
                  {ok['cod_rec'] ? <CheckCircle className="w-4 h-4 text-green" /> : <Save className="w-4 h-4" />}
                  {ok['cod_rec'] ? 'Salvo!' : saving['cod_rec'] ? 'Salvando...' : 'Aplicar'}
                </button>
              </div>
              {erro['cod_rec'] && (
                <p className="text-xs text-red-400 mt-1">{erro['cod_rec']}</p>
              )}
              {/* Preview dos registros E116 */}
              <div className="mt-3 space-y-1">
                {e116Pendencias.slice(0, 3).map((p, i) => (
                  <div key={i} className="text-xs font-mono text-gray-600 bg-bg3 px-2 py-1 rounded truncate">
                    L{p.linha}: {p.raw}
                  </div>
                ))}
                {e116Pendencias.length > 3 && (
                  <div className="text-xs text-gray-600">+ {e116Pendencias.length - 3} mais...</div>
                )}
              </div>
            </div>
          </div>
        </div>
      )}

      {/* ── Bloco CHV_NFE ── */}
      {chvPendencias.length > 0 && (
        <div className="bg-bg2 border border-border rounded-xl overflow-hidden">
          <div className="flex items-center gap-2 px-4 py-3 border-b border-border bg-bg3">
            <KeyRound className="w-4 h-4 text-red-400" />
            <span className="text-sm font-medium">C100 — Chave de Acesso NF-e/NFC-e ausente</span>
            <span className="ml-auto text-xs font-mono px-2 py-0.5 rounded bg-red-900/30 text-red-400">
              {chvPendencias.length} registro{chvPendencias.length !== 1 ? 's' : ''}
            </span>
          </div>

          <div className="divide-y divide-border">
            {chvPendencias.map((p, idx) => {
              const key = `chv_${p.linha}`
              const chv = chaves[p.linha] ?? ''
              const chvDigits = chv.replace(/\D/g, '')
              const chvOk = chvDigits.length === 44

              return (
                <div key={idx} className="p-4 space-y-3">
                  <div className="flex items-start justify-between gap-3">
                    <div>
                      <div className="flex items-center gap-2 mb-0.5">
                        <span className="text-xs font-mono font-medium text-white">
                          NF nº {p.num_doc}
                        </span>
                        <span className="text-xs font-mono text-gray-500">
                          MOD {p.cod_mod} · {p.dt_doc ? `${p.dt_doc.slice(0,2)}/${p.dt_doc.slice(2,4)}/${p.dt_doc.slice(4)}` : '—'}
                        </span>
                        <span className="text-xs font-mono px-1.5 py-0.5 rounded bg-red-900/20 text-red-400">
                          L{p.linha}
                        </span>
                      </div>
                      <div className="text-xs font-mono text-gray-600 truncate max-w-sm">{p.raw}</div>
                    </div>
                  </div>

                  <div className="flex gap-2 items-start flex-wrap">
                    <div className="flex-1 min-w-64">
                      <input
                        type="text"
                        maxLength={44}
                        value={chaves[p.linha] ?? ''}
                        onChange={e => setChaves(c => ({ ...c, [p.linha]: e.target.value.replace(/\D/g,'') }))}
                        placeholder="44 dígitos da chave de acesso"
                        className={`w-full px-3 py-2 rounded-lg border bg-bg3 text-xs font-mono text-white
                          placeholder-gray-600 focus:outline-none transition-colors
                          ${chv.length > 0 && !chvOk ? 'border-red-500' : chvOk ? 'border-green' : 'border-border2 focus:border-blue'}`}
                      />
                      <div className="flex justify-between mt-1">
                        <span className={`text-xs font-mono ${chv.length > 0 && !chvOk ? 'text-red-400' : chvOk ? 'text-green' : 'text-gray-600'}`}>
                          {chvDigits.length}/44 dígitos
                          {chvOk && ' ✓'}
                        </span>
                      </div>
                    </div>

                    <button
                      onClick={() => salvarChave(p.linha, 'inserir')}
                      disabled={!chvOk || saving[key]}
                      className="flex items-center gap-1.5 px-3 py-2 rounded-lg border border-blue/40 bg-blue/10 text-blue text-xs hover:bg-blue/20 transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
                    >
                      {ok[key] ? <CheckCircle className="w-3.5 h-3.5 text-green" /> : <Save className="w-3.5 h-3.5" />}
                      {ok[key] ? 'Salvo!' : saving[key] ? '...' : 'Inserir chave'}
                    </button>

                    <button
                      onClick={() => {
                        if (confirm(`Excluir NF nº ${p.num_doc} e todos seus itens (C170/C190)?\nEsta ação não pode ser desfeita.`))
                          salvarChave(p.linha, 'excluir')
                      }}
                      disabled={saving[key]}
                      className="flex items-center gap-1.5 px-3 py-2 rounded-lg border border-red-500/40 bg-red-500/10 text-red-400 text-xs hover:bg-red-500/20 transition-colors disabled:opacity-40"
                    >
                      <Trash2 className="w-3.5 h-3.5" />
                      Excluir registro
                    </button>
                  </div>

                  {erro[key] && (
                    <p className="text-xs text-red-400">{erro[key]}</p>
                  )}
                </div>
              )
            })}
          </div>
        </div>
      )}

      {/* ── Bloco Contribuições: M205/M605 COD_REC ── */}
      {contribPendencias.length > 0 && (
        <div className="bg-bg2 border border-border rounded-xl overflow-hidden">
          <div className="flex items-center gap-2 px-4 py-3 border-b border-border bg-bg3">
            <AlertCircle className="w-4 h-4 text-blue-400" />
            <span className="text-sm font-medium">M205/M605 — Código de Receita PIS/COFINS</span>
            <span className="ml-auto text-xs font-mono px-2 py-0.5 rounded bg-blue-900/30 text-blue-400">
              {contribPendencias.length} registro{contribPendencias.length !== 1 ? 's' : ''}
            </span>
          </div>
          <div className="p-4 space-y-2">
            <div className="text-xs text-gray-400 mb-3">
              Os registros abaixo precisam do COD_REC (código de receita) preenchido manualmente no arquivo.
            </div>
            {contribPendencias.map((p, i) => (
              <div key={i} className="flex items-center gap-3 bg-bg3 rounded-lg px-3 py-2">
                <span className={`text-xs font-mono px-1.5 py-0.5 rounded ${p.tipo === 'm205_cod_rec' ? 'bg-emerald-900/30 text-emerald-400' : 'bg-purple-900/30 text-purple-400'}`}>
                  {p.reg}
                </span>
                <span className="text-xs font-mono text-gray-500">L{p.linha}</span>
                <span className="text-xs text-gray-300 flex-1">{p.descricao}</span>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}
