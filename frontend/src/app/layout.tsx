import './globals.css';
import type { ReactNode } from 'react';

export const metadata = {
  title: 'AI Teaching Assistant Dashboard',
  description: 'Production-ready AI Teaching Assistant System',
};

export const viewport = {
  themeColor: '#020617',
};

const THEME_INIT_SCRIPT = `(function(){try{if(localStorage.getItem('theme')){document.documentElement.classList.toggle('dark',localStorage.getItem('theme')==='dark')}else{document.documentElement.classList.add('dark')}}catch(e){document.documentElement.classList.add('dark')}})()`;

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="en">
      <head>
        {/* Apply the saved theme before first paint to avoid a flash. */}
        <script dangerouslySetInnerHTML={{ __html: THEME_INIT_SCRIPT }} />
      </head>
      <body className="bg-app-bg font-sans text-app-text antialiased">{children}</body>
    </html>
  );
}
