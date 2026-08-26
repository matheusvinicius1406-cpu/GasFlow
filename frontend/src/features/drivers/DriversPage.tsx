import { UserCog } from 'lucide-react'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/Card'
import { Button } from '@/components/ui/Button'
import { Badge } from '@/components/ui/Badge'

const mockDrivers = [
  { codigo: '000001', nome: 'João Silva', telefone: '11999998888', placa: 'ABC-1234', ativo: true },
  { codigo: '000002', nome: 'Pedro Santos', telefone: '11988887777', placa: 'DEF-5678', ativo: true },
  { codigo: '000003', nome: 'Carlos Oliveira', telefone: '11977776666', placa: 'GHI-9012', ativo: true },
]

export function DriversPage() {
  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-foreground">Motoristas</h1>
          <p className="text-muted-foreground">Gerenciar motoristas da revenda</p>
        </div>
        <Button>
          <UserCog className="h-4 w-4" />
          Novo Motorista
        </Button>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Lista de Motoristas</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="space-y-4">
            {mockDrivers.map((driver) => (
              <div
                key={driver.codigo}
                className="flex items-center justify-between rounded-lg border border-border p-4 hover:bg-accent/50"
              >
                <div className="space-y-1">
                  <p className="font-medium text-foreground">{driver.nome}</p>
                  <p className="text-sm text-muted-foreground">
                    Código: {driver.codigo} • Placa: {driver.placa}
                  </p>
                  <p className="text-xs text-muted-foreground">{driver.telefone}</p>
                </div>
                <div className="flex items-center gap-4">
                  <Badge variant={driver.ativo ? 'success' : 'secondary'}>
                    {driver.ativo ? 'Ativo' : 'Inativo'}
                  </Badge>
                  <Button variant="ghost" size="sm">
                    Ver detalhes
                  </Button>
                </div>
              </div>
            ))}
          </div>
        </CardContent>
      </Card>
    </div>
  )
}
