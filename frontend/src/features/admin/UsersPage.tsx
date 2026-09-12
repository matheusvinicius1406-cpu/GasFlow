import { useCallback, useEffect, useMemo, useState } from 'react'
import { KeyRound, Pencil, Plus, Search, UserPlus, Users } from 'lucide-react'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/Card'
import { Badge } from '@/components/ui/Badge'
import { Button } from '@/components/ui/Button'
import { Input } from '@/components/ui/Input'
import { Select } from '@/components/ui/Select'
import { LoadingSpinner } from '@/components/ui/LoadingSpinner'
import { ErrorState } from '@/components/ui/ErrorState'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/Dialog'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/Table'
import { apiClient } from '@/lib/api/client'
import { useAuth } from '@/features/auth'

interface AdminUser {
  id: string
  username: string
  email: string
  display_name: string
  status: string
  role_id: string | null
  must_change_password: boolean
  last_login_at: string | null
  created_at: string | null
}

interface AdminRole {
  id: string
  name: string
  system_role: string
  permissions: string[]
}

interface UsersResponse {
  users: AdminUser[]
}

interface RolesResponse {
  roles: AdminRole[]
}

type DialogMode =
  | { kind: 'closed' }
  | { kind: 'create' }
  | { kind: 'edit'; user: AdminUser }
  | { kind: 'reset'; user: AdminUser }

export function UsersPage() {
  const { hasPermission } = useAuth()
  const [users, setUsers] = useState<AdminUser[]>([])
  const [roles, setRoles] = useState<AdminRole[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(false)
  const [search, setSearch] = useState('')
  const [roleFilter, setRoleFilter] = useState('')
  const [statusFilter, setStatusFilter] = useState('')
  const [dialog, setDialog] = useState<DialogMode>({ kind: 'closed' })
  const [toast, setToast] = useState<{ kind: 'ok' | 'err'; text: string } | null>(null)
  const [tempPassword, setTempPassword] = useState<string | null>(null)

  // Permissões individuais (a página exige user.read; as ações, as próprias).
  const canCreate = hasPermission('user.create')
  const canEdit = hasPermission('user.update')
  const canReset = hasPermission('user.reset_password')
  const canDeactivate = hasPermission('user.deactivate')

  const fetchUsers = useCallback(async () => {
    setLoading(true)
    setError(false)
    try {
      const { data } = await apiClient.get<UsersResponse>('/admin/users')
      setUsers(data.users)
    } catch {
      setError(true)
    } finally {
      setLoading(false)
    }
  }, [])

  const fetchRoles = useCallback(async () => {
    try {
      const { data } = await apiClient.get<RolesResponse>('/admin/roles')
      setRoles(data.roles)
    } catch {
      // Sem role.manage — página ainda lista usuários, filtro de role fica vazio.
    }
  }, [])

  useEffect(() => {
    fetchUsers()
    fetchRoles()
  }, [fetchUsers, fetchRoles])

  const roleNameById = useMemo(() => {
    const map = new Map<string, string>()
    for (const r of roles) map.set(r.id, r.name)
    return map
  }, [roles])

  const filtered = useMemo(() => {
    const q = search.trim().toLowerCase()
    return users.filter((u) => {
      if (q) {
        const haystack = `${u.username} ${u.email} ${u.display_name}`.toLowerCase()
        if (!haystack.includes(q)) return false
      }
      if (roleFilter && u.role_id !== roleFilter) return false
      if (statusFilter && u.status !== statusFilter) return false
      return true
    })
  }, [users, search, roleFilter, statusFilter])

  const notify = (kind: 'ok' | 'err', text: string) => {
    setToast({ kind, text })
    window.setTimeout(() => setToast(null), 4000)
  }

  const handleToggleStatus = async (user: AdminUser) => {
    try {
      const endpoint =
        user.status === 'ACTIVE'
          ? `/admin/users/${user.id}/deactivate`
          : `/admin/users/${user.id}/activate`
      await apiClient.post(endpoint)
      notify('ok', user.status === 'ACTIVE' ? 'Usuário desativado.' : 'Usuário ativado.')
      fetchUsers()
    } catch (err: unknown) {
      const detail = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail
      notify('err', detail || 'Falha ao alterar status.')
    }
  }

  const handleResetPassword = async (user: AdminUser) => {
    try {
      const { data } = await apiClient.post<{ temporary_password: string }>(
        `/admin/users/${user.id}/reset-password`
      )
      setTempPassword(data.temporary_password)
      notify('ok', 'Senha temporária gerada — mostre ao usuário agora.')
      fetchUsers()
    } catch (err: unknown) {
      const detail = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail
      notify('err', detail || 'Falha ao resetar senha.')
    }
  }

  const statusBadge = (status: string) =>
    status === 'ACTIVE' ? (
      <Badge variant="success">Ativo</Badge>
    ) : status === 'DISABLED' ? (
      <Badge variant="destructive">Inativo</Badge>
    ) : (
      <Badge variant="warning">{status}</Badge>
    )

  if (loading) {
    return (
      <div className="flex items-center justify-center py-16">
        <LoadingSpinner size="lg" />
      </div>
    )
  }

  if (error) {
    return <ErrorState message="Não foi possível carregar os usuários." onRetry={fetchUsers} />
  }

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="flex items-center gap-2 text-xl font-semibold">
            <Users className="h-6 w-6" /> Usuários
          </h1>
          <p className="text-sm text-muted-foreground">
            Gestão de usuários, senhas e papéis (RBAC).
          </p>
        </div>
        {canCreate && (
          <Button onClick={() => setDialog({ kind: 'create' })}>
            <UserPlus className="h-4 w-4" /> Novo usuário
          </Button>
        )}
      </div>

      {/* Filtros */}
      <div className="flex flex-wrap gap-2">
        <div className="relative min-w-56 flex-1">
          <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
          <Input
            placeholder="Buscar por nome, e-mail..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="pl-9"
            aria-label="Buscar usuários"
          />
        </div>
        <Select
          value={roleFilter}
          onChange={(e) => setRoleFilter(e.target.value)}
          className="w-44"
          aria-label="Filtrar por papel"
        >
          <option value="">Todos os papéis</option>
          {roles.map((r) => (
            <option key={r.id} value={r.id}>
              {r.name}
            </option>
          ))}
        </Select>
        <Select
          value={statusFilter}
          onChange={(e) => setStatusFilter(e.target.value)}
          className="w-40"
          aria-label="Filtrar por status"
        >
          <option value="">Todos os status</option>
          <option value="ACTIVE">Ativos</option>
          <option value="DISABLED">Inativos</option>
          <option value="LOCKED">Bloqueados</option>
        </Select>
      </div>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">
            {filtered.length} de {users.length} usuários
          </CardTitle>
        </CardHeader>
        <CardContent>
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Usuário</TableHead>
                <TableHead>Papel</TableHead>
                <TableHead>Status</TableHead>
                <TableHead>Último login</TableHead>
                <TableHead className="text-right">Ações</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {filtered.map((u) => (
                <TableRow key={u.id}>
                  <TableCell>
                    <div className="font-medium">{u.display_name || u.username}</div>
                    <div className="text-xs text-muted-foreground">
                      @{u.username} · {u.email}
                    </div>
                    {u.must_change_password && (
                      <Badge variant="warning" className="mt-1 text-[10px]">
                        deve trocar a senha
                      </Badge>
                    )}
                  </TableCell>
                  <TableCell>
                    {u.role_id ? (
                      <Badge variant="secondary">{roleNameById.get(u.role_id) ?? '—'}</Badge>
                    ) : (
                      <span className="text-xs text-muted-foreground">—</span>
                    )}
                  </TableCell>
                  <TableCell>{statusBadge(u.status)}</TableCell>
                  <TableCell className="text-xs text-muted-foreground">
                    {u.last_login_at ? new Date(u.last_login_at).toLocaleString('pt-BR') : 'nunca'}
                  </TableCell>
                  <TableCell>
                    <div className="flex justify-end gap-1">
                      {canEdit && (
                        <Button
                          variant="ghost"
                          size="icon"
                          title="Editar"
                          aria-label={`Editar ${u.username}`}
                          onClick={() => setDialog({ kind: 'edit', user: u })}
                        >
                          <Pencil className="h-4 w-4" />
                        </Button>
                      )}
                      {canReset && (
                        <Button
                          variant="ghost"
                          size="icon"
                          title="Resetar senha"
                          aria-label={`Resetar senha de ${u.username}`}
                          onClick={() => {
                            setTempPassword(null)
                            setDialog({ kind: 'reset', user: u })
                          }}
                        >
                          <KeyRound className="h-4 w-4" />
                        </Button>
                      )}
                      {canDeactivate && (
                        <Button
                          variant={u.status === 'ACTIVE' ? 'ghost' : 'outline'}
                          size="sm"
                          onClick={() => handleToggleStatus(u)}
                        >
                          {u.status === 'ACTIVE' ? 'Desativar' : 'Ativar'}
                        </Button>
                      )}
                    </div>
                  </TableCell>
                </TableRow>
              ))}
              {filtered.length === 0 && (
                <TableRow>
                  <TableCell colSpan={5} className="py-8 text-center text-muted-foreground">
                    Nenhum usuário encontrado com os filtros atuais.
                  </TableCell>
                </TableRow>
              )}
            </TableBody>
          </Table>
        </CardContent>
      </Card>

      {/* Modais */}
      {dialog.kind === 'create' && (
        <UserFormDialog
          roles={roles}
          onClose={() => setDialog({ kind: 'closed' })}
          onSaved={(msg) => {
            setDialog({ kind: 'closed' })
            notify('ok', msg)
            fetchUsers()
          }}
        />
      )}
      {dialog.kind === 'edit' && (
        <UserFormDialog
          roles={roles}
          user={dialog.user}
          onClose={() => setDialog({ kind: 'closed' })}
          onSaved={(msg) => {
            setDialog({ kind: 'closed' })
            notify('ok', msg)
            fetchUsers()
          }}
        />
      )}
      {dialog.kind === 'reset' && (
        <Dialog open onOpenChange={(open) => !open && setDialog({ kind: 'closed' })}>
          <DialogContent>
            <DialogHeader>
              <DialogTitle>Resetar senha</DialogTitle>
              <DialogDescription>
                A senha atual de <strong>@{dialog.user.username}</strong> será invalidada e uma
                temporária será gerada. O usuário deverá trocá-la no próximo login.
              </DialogDescription>
            </DialogHeader>
            {tempPassword ? (
              <div className="space-y-3">
                <div className="rounded-md border border-warning/40 bg-warning/10 p-3 text-center">
                  <div className="text-xs text-muted-foreground">Senha temporária (mostre uma vez):</div>
                  <div className="select-all font-mono text-lg font-bold tracking-widest">
                    {tempPassword}
                  </div>
                </div>
                <DialogFooter>
                  <Button onClick={() => setDialog({ kind: 'closed' })}>Concluído</Button>
                </DialogFooter>
              </div>
            ) : (
              <DialogFooter>
                <Button variant="outline" onClick={() => setDialog({ kind: 'closed' })}>
                  Cancelar
                </Button>
                <Button onClick={() => handleResetPassword(dialog.user)}>Gerar senha temporária</Button>
              </DialogFooter>
            )}
          </DialogContent>
        </Dialog>
      )}

      {toast && (
        <div
          role="status"
          className={`fixed bottom-4 right-4 z-50 rounded-md border px-4 py-2 text-sm shadow-lg ${
            toast.kind === 'ok'
              ? 'border-success/40 bg-success/10 text-success'
              : 'border-destructive/40 bg-destructive/10 text-destructive'
          }`}
        >
          {toast.text}
        </div>
      )}
    </div>
  )
}

// ── Modal de criação/edição ─────────────────────────────

interface UserFormDialogProps {
  roles: AdminRole[]
  user?: AdminUser
  onClose: () => void
  onSaved: (message: string) => void
}

function UserFormDialog({ roles, user, onClose, onSaved }: UserFormDialogProps) {
  const isEdit = !!user
  const [username, setUsername] = useState(user?.username ?? '')
  const [email, setEmail] = useState(user?.email ?? '')
  const [displayName, setDisplayName] = useState(user?.display_name ?? '')
  const [roleId, setRoleId] = useState(user?.role_id ?? roles[0]?.id ?? '')
  const [password, setPassword] = useState('')
  const [saving, setSaving] = useState(false)
  const [formError, setFormError] = useState<string | null>(null)

  const generateRandom = () => {
    const alphabet = 'ABCDEFGHJKLMNPQRSTUVWXYZ23456789'
    const pick = (n: number) =>
      Array.from({ length: n }, () => alphabet[Math.floor(Math.random() * alphabet.length)]).join('')
    setPassword(`${pick(4)}-${pick(4)}-${pick(4)}`)
  }

  const submit = async () => {
    setSaving(true)
    setFormError(null)
    try {
      if (isEdit && user) {
        await apiClient.patch(`/admin/users/${user.id}`, {
          username,
          email,
          display_name: displayName,
          role_id: roleId || null,
        })
        onSaved('Usuário atualizado.')
      } else {
        await apiClient.post('/admin/users', {
          username,
          email,
          password,
          display_name: displayName,
          role_id: roleId || null,
        })
        onSaved('Usuário criado.')
      }
    } catch (err: unknown) {
      const detail = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail
      setFormError(typeof detail === 'string' ? detail : 'Falha ao salvar usuário.')
    } finally {
      setSaving(false)
    }
  }

  return (
    <Dialog open onOpenChange={(open) => !open && onClose()}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{isEdit ? 'Editar usuário' : 'Novo usuário'}</DialogTitle>
          <DialogDescription>
            {isEdit
              ? `Alterando dados de @${user.username}.`
              : 'O usuário deverá trocar a senha no primeiro login.'}
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-3">
          <label className="block space-y-1">
            <span className="text-sm font-medium">Usuário</span>
            <Input value={username} onChange={(e) => setUsername(e.target.value)} minLength={3} />
          </label>
          <label className="block space-y-1">
            <span className="text-sm font-medium">E-mail</span>
            <Input type="email" value={email} onChange={(e) => setEmail(e.target.value)} />
          </label>
          <label className="block space-y-1">
            <span className="text-sm font-medium">Nome de exibição</span>
            <Input value={displayName} onChange={(e) => setDisplayName(e.target.value)} />
          </label>
          <label className="block space-y-1">
            <span className="text-sm font-medium">Papel</span>
            <Select value={roleId} onChange={(e) => setRoleId(e.target.value)}>
              <option value="">Sem papel</option>
              {roles.map((r) => (
                <option key={r.id} value={r.id}>
                  {r.name}
                </option>
              ))}
            </Select>
          </label>
          {!isEdit && (
            <label className="block space-y-1">
              <span className="flex items-center justify-between text-sm font-medium">
                Senha inicial
                <button
                  type="button"
                  className="text-xs text-primary underline-offset-2 hover:underline"
                  onClick={generateRandom}
                >
                  <Plus className="mr-1 inline h-3 w-3" />
                  gerar aleatória
                </button>
              </span>
              <Input
                type="text"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                placeholder="mínimo 6 caracteres"
              />
            </label>
          )}
          {formError && (
            <p className="text-sm text-destructive" role="alert">
              {formError}
            </p>
          )}
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={onClose} disabled={saving}>
            Cancelar
          </Button>
          <Button onClick={submit} disabled={saving || !username || !email || (!isEdit && !password)}>
            {saving ? 'Salvando…' : 'Salvar'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
