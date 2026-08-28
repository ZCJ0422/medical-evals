"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { ActivityIcon, CheckIcon } from "../components/icons";
import { currentUser, hasToken, logout } from "../lib/auth";
import type { User } from "../lib/types";

export default function HomePage() {
  const [user, setUser] = useState<User | null>(null);

  useEffect(() => {
    if (!hasToken()) return;
    currentUser().then(setUser).catch(() => setUser(null));
  }, []);

  async function signOut() {
    await logout();
    setUser(null);
  }

  return <main className="public-site">
    <nav className="public-nav" aria-label="主导航"><Link className="public-brand" href="/"><span className="brand-mark"><ActivityIcon size={18} /></span><span>Medical Evals</span></Link><div className="public-nav-links"><a href="#datasets">评测数据集</a><a href="#rankings">评测榜单</a><a href="#docs">文档</a>{user ? <div className="account-menu"><button className="account-avatar" type="button" aria-label="打开账号菜单">{user.username.slice(0, 1).toUpperCase()}</button><div className="account-popover"><strong>{user.username}</strong><span>公众用户</span><Link href="/portal">测评空间</Link><button type="button" onClick={() => void signOut()}>退出登录</button></div></div> : <Link className="nav-login" href="/login">登录</Link>}</div></nav>
    <section className="brand-hero"><div className="brand-hero-copy"><h1>Medical <span>Evals</span></h1><p>评测医疗大模型在真实世界中的能力</p></div><div className="brand-hero-art" aria-label="评测榜单与分数示意"><div className="art-glow" /><div className="art-orbit art-orbit-a" /><div className="art-orbit art-orbit-b" /><div className="art-score"><span>综合能力评测</span><strong>86.4<small>分</small></strong><div className="art-score-line"><i /><i /><i /><i /><i /></div><em>HealthBench · 已完成</em></div><div className="art-rank"><span>当前榜单</span><strong>Top 10</strong><small>医疗大模型</small></div><div className="art-status"><CheckIcon size={14} /> 评测结果已同步</div></div></section>
  </main>;
}
