import { type LucideIcon, Construction } from 'lucide-react'
import { Card, CardContent } from '@/components/ui/Card'

interface ModulePlaceholderProps {
  icon: LucideIcon
  title: string
  description: string
}

export function ModulePlaceholder({ icon: Icon, title, description }: ModulePlaceholderProps) {
  return (
    <div className="flex flex-col items-center justify-center py-16">
      <Card className="w-full max-w-md">
        <CardContent className="flex flex-col items-center p-8 text-center">
          <div className="rounded-full bg-primary/10 p-4">
            <Icon className="h-12 w-12 text-primary" />
          </div>
          <h2 className="mt-6 text-xl font-bold text-foreground">{title}</h2>
          <p className="mt-2 text-sm text-muted-foreground">{description}</p>
          <div className="mt-6 flex items-center gap-2 rounded-md bg-muted px-4 py-2">
            <Construction className="h-4 w-4 text-muted-foreground" />
            <span className="text-sm text-muted-foreground">Módulo em construção</span>
          </div>
        </CardContent>
      </Card>
    </div>
  )
}
