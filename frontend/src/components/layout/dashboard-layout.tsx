'use client';

import { ReactNode, memo } from 'react';
import Link from 'next/link';
import { usePathname } from 'next/navigation';
import {
  LayoutDashboard,
  TrendingUp,
  Wallet,
  Settings,
  Bell,
  Wifi,
  WifiOff,
  Radio,
  PieChart,
  LineChart,
  HelpCircle,
} from 'lucide-react';
import { cn } from '@/lib/utils';
import { Button } from '@/components/ui/button';
import { useWebSocket } from '@/lib/websocket';

const navigation = [
  { name: 'Dashboard', href: '/', icon: LayoutDashboard },
  { name: 'Situation Room', href: '/situation-room', icon: Radio },
  { name: 'Funding Rates', href: '/funding-rates', icon: LineChart },
  { name: 'Opportunities', href: '/opportunities', icon: TrendingUp },
  { name: 'Positions', href: '/positions', icon: Wallet },
  { name: 'Performance', href: '/performance', icon: PieChart },
  { name: 'Settings', href: '/settings', icon: Settings },
  { name: 'Help', href: '/help', icon: HelpCircle },
];

// Separate component for connection status to isolate re-renders
const ConnectionStatus = memo(function ConnectionStatus() {
  const { isConnected } = useWebSocket();

  return (
    <div className="border-t p-4">
      <div className="flex items-center gap-2 text-sm">
        {isConnected ? (
          <>
            <Wifi className="h-4 w-4 text-green-500" />
            <span className="text-green-500">Connected</span>
          </>
        ) : (
          <>
            <WifiOff className="h-4 w-4 text-red-500" />
            <span className="text-red-500">Disconnected</span>
          </>
        )}
      </div>
    </div>
  );
});

// Navigation links component
const NavigationLinks = memo(function NavigationLinks() {
  const pathname = usePathname();

  return (
    <nav className="flex-1 space-y-1 px-3 py-4">
      {navigation.map((item) => {
        const isActive = pathname === item.href;
        return (
          <Link
            key={item.name}
            href={item.href}
            className={cn(
              'flex items-center gap-3 rounded-lg px-3 py-2 text-sm font-medium transition-colors',
              isActive
                ? 'bg-primary text-primary-foreground'
                : 'text-muted-foreground hover:bg-accent hover:text-accent-foreground'
            )}
          >
            <item.icon className="h-5 w-5" />
            {item.name}
          </Link>
        );
      })}
    </nav>
  );
});

export function DashboardLayout({ children }: { children: ReactNode }) {
  return (
    <div className="flex h-screen bg-background">
      {/* Sidebar */}
      <div className="hidden w-64 flex-shrink-0 border-r bg-card md:block">
        <div className="flex h-full flex-col">
          {/* Logo */}
          <div className="flex h-16 items-center border-b px-6">
            <span className="text-xl font-bold">NEXUS</span>
          </div>

          {/* Navigation */}
          <NavigationLinks />

          {/* Connection Status */}
          <ConnectionStatus />
        </div>
      </div>

      {/* Main Content */}
      <div className="flex flex-1 flex-col overflow-hidden">
        {/* Header */}
        <header className="flex h-16 items-center justify-between border-b px-6">
          <div className="flex items-center gap-4 md:hidden">
            <span className="text-xl font-bold">NEXUS</span>
          </div>

          <div className="flex items-center gap-4 ml-auto">
            <Button variant="ghost" size="icon">
              <Bell className="h-5 w-5" />
            </Button>
          </div>
        </header>

        {/* Page Content */}
        <main className="flex-1 overflow-y-auto p-6">{children}</main>
      </div>
    </div>
  );
}
