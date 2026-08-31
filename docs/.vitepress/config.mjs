import {defineConfig} from 'vitepress'
import {withMermaid} from 'vitepress-plugin-mermaid'

// https://vitepress.dev/reference/site-config
export default withMermaid(defineConfig({
    title: "中文社交平台聚合搜索",
    description: "同时搜索小红书、抖音、B站和知乎的跨平台聚合搜索工具。",
    lastUpdated: true,
    base: '/MediaCrawler/',
    head: [
        [
            'script',
            {async: '', src: 'https://www.googletagmanager.com/gtag/js?id=G-5TK7GF3KK1'}
        ],
        [
            'script',
            {},
            `window.dataLayer = window.dataLayer || [];
      function gtag(){dataLayer.push(arguments);}
      gtag('js', new Date());
      gtag('config', 'G-5TK7GF3KK1');`
        ]
    ],
    themeConfig: {
        editLink: {
            pattern: 'https://github.com/KellenGO/MediaCrawler/tree/master/docs/:path'
        },
        search: {
            provider: 'local'
        },
        // https://vitepress.dev/reference/default-theme-config
        nav: [
            {text: '首页', link: '/'},
            {text: '账号与浏览器', link: '/CDP模式使用指南'},
        ],

        sidebar: [
            {
                text: '聚合搜索产品',
                link: '/',
            },
            {
                text: '使用说明',
                items: [
                    {text: '基本使用', link: '/'},
                    {text: '常见问题汇总', link: '/常见问题'},
                    {text: 'IP代理使用', link: '/代理使用'},
                    {text: '手机号登录说明', link: '/手机号登录说明'},
                ]
            },

        ],

        socialLinks: [
            {icon: 'github', link: 'https://github.com/KellenGO/MediaCrawler'}
        ]
    }
}))
