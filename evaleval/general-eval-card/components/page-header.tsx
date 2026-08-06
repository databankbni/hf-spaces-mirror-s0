interface PageHeaderProps {
  title: string
  description?: string
  eyebrow?: string
  metaItems?: Array<{
    label: string
    value: string
  }>
  size?: "default" | "wide"
  children?: React.ReactNode
}

export function PageHeader({
  title,
  description,
  eyebrow,
  metaItems = [],
  children,
}: PageHeaderProps) {
  return (
    <div className="motion-academic-enter border-b border-[color:var(--border-soft)] bg-background">
      <div className="mx-auto w-full max-w-[96rem] px-4 pt-12 pb-10 sm:px-8">
        <div className="grid gap-10 lg:grid-cols-[minmax(0,1fr)_auto] lg:items-end">
          <div>
            {eyebrow && <div className="kicker">{eyebrow}</div>}
            <h1 className="ec-page-h1">{title}</h1>
            {description && <p className="ec-page-lede">{description}</p>}
          </div>

          {(children || metaItems.length > 0) && (
            <div className="flex flex-col gap-3 lg:items-end">
              {children && <div className="flex flex-wrap items-center gap-2">{children}</div>}
              {metaItems.length > 0 && (
                <div className="flex flex-wrap gap-2 lg:justify-end">
                  {metaItems.map((item) => (
                    <div key={`${item.label}-${item.value}`} className="ec-page-meta-item">
                      <span className="ec-page-meta-item-l">{item.label}</span>
                      <span className="ec-page-meta-item-v">{item.value}</span>
                    </div>
                  ))}
                </div>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
