import { ReactNode } from 'react'

interface CardProps {
  children: ReactNode
  className?: string
  padding?: boolean
}

interface CardHeaderProps {
  children: ReactNode
  className?: string
}

interface CardContentProps {
  children: ReactNode
  className?: string
}

interface CardFooterProps {
  children: ReactNode
  className?: string
}

export function Card({ children, className = '', padding = true }: CardProps) {
  return (
    <div className={`card ${padding ? 'p-6' : ''} ${className}`}>
      {children}
    </div>
  )
}

export function CardHeader({ children, className = '' }: CardHeaderProps) {
  return (
    <div className={`card-header ${className}`}>
      {children}
    </div>
  )
}

export function CardContent({ children, className = '' }: CardContentProps) {
  return (
    <div className={`card-content ${className}`}>
      {children}
    </div>
  )
}

export function CardFooter({ children, className = '' }: CardFooterProps) {
  return (
    <div className={`px-6 py-4 border-t border-gray-200 dark:border-gray-700 ${className}`}>
      {children}
    </div>
  )
}

Card.Header = CardHeader
Card.Content = CardContent
Card.Footer = CardFooter