import { ExternalLink } from 'lucide-react'

const ORIGINAL_PROJECT_URL = 'https://github.com/NanmiCoder/MediaCrawler'
const CURRENT_PROJECT_URL = 'https://github.com/KellenGO/MediaCrawler'

interface HelpPageProps {
  onShowDisclaimer: () => void
}

export function HelpPage({ onShowDisclaimer }: HelpPageProps) {
  return (
    <div className="preview-container help-page">
      <div className="page-heading">
        <div>
          <p className="eyebrow">HELP &amp; ABOUT</p>
          <h1>从第一次搜索开始</h1>
          <p className="description">连接本机服务和浏览器扩展，把四个平台放进同一个搜索流程。</p>
        </div>
      </div>

      <div className="help-grid">
        <section className="help-section">
          <h2>使用流程</h2>
          <ol className="steps">
            <li><strong>启动本机服务</strong>保持 MediaCrawler 后端运行，网页会自动检查连接状态。</li>
            <li><strong>连接平台账号</strong>在常用浏览器登录平台，再通过扩展同步登录状态。</li>
            <li><strong>开始聚合搜索</strong>输入关键词、选择平台，已返回的内容可以边搜边看。</li>
            <li><strong>收藏与整理</strong>保存到本地收藏，添加备注，或导出一份备份。</li>
          </ol>
        </section>

        <section className="help-section">
          <h2>安装浏览器扩展</h2>
          <ol>
            <li>打开 <code>chrome://extensions</code>，Edge 使用 <code>edge://extensions</code>。</li>
            <li>开启“开发者模式”，点击“加载已解压的扩展程序”。</li>
            <li>选择项目中的 <code>browser_extension</code> 文件夹。</li>
            <li>刷新四野页面，然后到“设置 · 账号与登录”检查连接。</li>
          </ol>
        </section>

        <section className="help-section">
          <h2>两种收藏</h2>
          <p><strong>本地收藏</strong>保存你从搜索结果中选中的内容，可写备注、筛选和备份。</p>
          <p className="mt-3"><strong>跨平台收藏</strong>从已登录平台读取收藏列表，并允许再保存到本地。同步不会添加、删除或移动平台中的收藏。</p>
        </section>

        <section className="help-section">
          <h2>项目与作者</h2>
          <p>当前界面与功能由 KellenGong 维护，基础采集能力来自 MediaCrawler 原项目。</p>
          <div className="button-row">
            <a className="text-link" href={CURRENT_PROJECT_URL} target="_blank" rel="noreferrer">当前项目 <ExternalLink /></a>
            <a className="text-link" href={ORIGINAL_PROJECT_URL} target="_blank" rel="noreferrer">原项目 <ExternalLink /></a>
          </div>
        </section>

        <section className="help-section wide" id="disclaimer">
          <h2>使用须知</h2>
          <p>请在法律与平台规则允许的范围内使用。本项目仅用于学习和研究；账号、收藏与搜索数据均由本机服务处理。使用前请阅读完整免责声明。</p>
          <div className="button-row"><button className="btn" type="button" onClick={onShowDisclaimer}>查看完整使用须知</button></div>
        </section>
      </div>
    </div>
  )
}
