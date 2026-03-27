'use client'
import { useEffect, useState } from 'react'
import { Trash2, Download, Eye } from 'lucide-react'

interface Props { onSelect: (id: number) => void }

export default function Historico({ onSelect }: Props) {
  const [itens, setItens] = useState<any[]>([])
  const [loading, setLoading] = useState(true)

  const carregar = async () => {
    setLoading(true)
    try {
      const r = await fetch('/api/historico')
      setItens(await r.json())
    } finally { setLoading(false) }
  }

  useEffect(() => { carregar() }, [])

  const deletar = async (id: number) => {
    if (!confirm('Remover este processamento?')) return
    await fetch(`/api/processamento/${id}`, { method: 'DELETE' })
    carregar()
  }

  if (loading) return <div className="text-gray-600 text-sm p-4">Carregando histórico...</div>
  if (!itens.length) return (
    <div className="flex flex-col items-center justify-center h-64 gap-3 text-gray-600">
      <div className="text-4xl opacity-10">📂</div>
      <p className="text-sm">Nenhum arquivo processado ainda</p>
    </div>
  )

  const fmtN = (n: number) => n?.toLocaleString('pt-BR') ?? '—'

  return (
    <div className="space-y-3">
      <div className="text-xs uppercase tracking-widest text-gray-500 mb-4">
        {itens.length} processamento{itens.length !== 1 ? 's' : ''}
      </div>
      {itens.map(item => (
        <div key={item.id}
          className="bg-bg2 border border-border hover:border-border2 rounded-xl p-4 transition-colors">
          <div className="flex items-start justify-between gap-4">
            <div className="flex-1 min-w-0">
              <div className="flex items-center gap-2 mb-1 flex-wrap">
                <span className="font-medium text-sm truncate">{item.nome}</span>
                <span className="text-xs font-mono px-2 py-0.5 rounded bg-bg3 border border-border text-gray-400">
                  {item.uf}
                </span>
                <span className="text-xs font-mono text-gray-600">v{item.versao}</span>
              </div>
              <div className="flex items-center gap-4 text-xs font-mono text-gray-500 mb-3">
                <span>{item.cnpj}</span>
                <span>{item.dt_ini} – {item.dt_fin}</span>
                <span>{new Date(item.criado_em).toLocaleDateString('pt-BR')}</span>
              </div>
              <div className="flex gap-3 text-xs">
                <span className="flex items-center gap-1">
                  <span className="w-2 h-2 rounded-full bg-red-400 shadow-[0_0_4px_#ff4757]" />
                  <span className="text-red-400 font-mono">{item.total_erros}</span>
                  <span className="text-gray-600">erros</span>
                </span>
                <span className="flex items-center gap-1">
                  <span className="w-2 h-2 rounded-full bg-purple-400" />
                  <span className="text-purple-400 font-mono">{item.total_fixes}</span>
                  <span className="text-gray-600">corrigidos</span>
                </span>
                <span className="flex items-center gap-1">
                  <span className="w-2 h-2 rounded-full bg-amber-400" />
                  <span className="text-amber-400 font-mono">{item.total_flags}</span>
                  <span className="text-gray-600">flags</span>
                </span>
                <span className="flex items-center gap-1">
                  <span className="text-gray-500 font-mono">{fmtN(item.total_linhas)}</span>
                  <span className="text-gray-600">linhas</span>
                </span>
              </div>
            </div>
            <div className="flex items-center gap-2 flex-shrink-0">
              <a href={`/api/download/${item.id}`}
                className="p-2 rounded-lg border border-border2 hover:bg-bg3 transition-colors text-gray-400 hover:text-green"
                title="Baixar corrigido">
                <Download className="w-4 h-4" />
              </a>
              <button onClick={() => onSelect(item.id)}
                className="p-2 rounded-lg border border-border2 hover:bg-bg3 transition-colors text-gray-400 hover:text-blue-400"
                title="Ver resultado">
                <Eye className="w-4 h-4" />
              </button>
              <button onClick={() => deletar(item.id)}
                className="p-2 rounded-lg border border-border2 hover:bg-bg3 transition-colors text-gray-400 hover:text-red-400"
                title="Remover">
                <Trash2 className="w-4 h-4" />
              </button>
            </div>
          </div>
        </div>
      ))}
    </div>
  )
}
