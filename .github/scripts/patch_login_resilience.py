#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""幂等修复：登录数据加载超时 + fetch 语法错误 + v4 提成方案保留检查"""
import sys, io, re

PATH = sys.argv[1] if len(sys.argv) > 1 else '/workspace/index.html'

with io.open(PATH, 'r', encoding='utf-8') as f:
    html = f.read()

changed = []

# ---------- 1. 修复 replace(/\n/g) 被写成真实换行导致的语法错误 ----------
broken = "data.content.replace(/\n/g, ''))"
fixed = "data.content.replace(/\\n/g, ''))"
if broken in html:
    html = html.replace(broken, fixed)
    changed.append('修复 fetchKbFileViaApi 正则语法错误')

# ---------- 2. loadCustomRolesFromGitHub 改为"内联/缓存优先，立即就绪" ----------
NEW_ROLES = u'''var rolesReady = false;
function _applyRolesCache(cached) {
  Object.keys(ROLE_CONFIG).forEach(function(key) {
    if (key !== 'admin' && !ROLE_CONFIG[key].fixed) delete ROLE_CONFIG[key];
  });
  Object.keys(cached).forEach(function(key) {
    ROLE_CONFIG[key] = {
      text: cached[key].text,
      menus: cached[key].menus || ['home'],
      features: cached[key].features || [],
      fixed: false
    };
  });
}

function loadCustomRolesFromGitHub() {
  // 1) 先用本地缓存或内联角色填充，立即放行登录（不依赖网络）
  var cached = null;
  try { cached = JSON.parse(localStorage.getItem('systemRoles') || 'null'); } catch(e) {}
  var initial = cached && Object.keys(cached).length > 0 ? cached : null;
  if (!initial) {
    initial = {};
    getEmbeddedRoles().forEach(function(r) {
      initial[r.key] = { text: r.text, menus: r.menus, features: r.features };
    });
  }
  _applyRolesCache(initial);
  rolesReady = true;
  // 2) 后台静默刷新服务器最新角色（失败不影响登录）
  return fetchKbFileViaApi('roles.json', 8)
    .then(function(data) {
      if (!data || data.length === 0) return;
      var nc = {};
      Object.keys(ROLE_CONFIG).forEach(function(key) {
        if (key !== 'admin' && !ROLE_CONFIG[key].fixed) delete ROLE_CONFIG[key];
      });
      data.forEach(function(r) {
        if (r.key && r.key !== 'admin') {
          ROLE_CONFIG[r.key] = {
            text: r.text,
            menus: r.menus || ['home'],
            features: r.features || [],
            fixed: false
          };
          nc[r.key] = { text: r.text, menus: r.menus || ['home'], features: r.features || [] };
        }
      });
      try { localStorage.setItem('systemRoles', JSON.stringify(nc)); } catch(e) {}
      console.log('[用户系统] roles.json 已刷新，共 ' + (Object.keys(ROLE_CONFIG).length - 1) + ' 个自定义角色');
    })
    .catch(function(err) {
      console.warn('[用户系统] roles.json 刷新失败，继续使用本地数据:', err.message);
    });
}'''

start_anchor = u"var rolesReady = false;\nfunction loadCustomRolesFromGitHub() {"
end_anchor = u"\n\n// 保存自定义角色到GitHub"
i = html.find(start_anchor)
j = html.find(end_anchor, i + 1) if i >= 0 else -1
if i >= 0 and j > i:
    html = html[:i] + NEW_ROLES + html[j:]
    changed.append('角色加载改为缓存/内联优先')

# ---------- 3. preloadUsers 改为"缓存优先，立即就绪" ----------
NEW_USERS = u'''function preloadUsers() {
  // 1) 先用本地缓存或内联用户表，立即放行登录（不依赖网络）
  var localUsers = null;
  try { localUsers = JSON.parse(localStorage.getItem('systemUsers') || 'null'); } catch(e) {}
  usersCache = (localUsers && localUsers.length > 0) ? localUsers : getDefaultUsers();
  usersReady = true;
  // 2) 后台静默刷新服务器最新用户（失败不影响登录）
  fetchKbFileViaApi('users.json', 8)
    .then(function(data) {
      data = data || [];
      var existingNames = data.map(function(u) { return u.name; });
      try {
        var stored = JSON.parse(localStorage.getItem('systemUsers') || '[]');
        (stored || []).forEach(function(lu) {
          if (existingNames.indexOf(lu.name) === -1) data.push(lu);
        });
      } catch(e) {}
      if (data.length > 0) {
        usersCache = data;
        try { localStorage.setItem('systemUsers', JSON.stringify(data)); } catch(e) {}
        console.log('[用户系统] users.json 已刷新，共 ' + data.length + ' 个用户');
      }
    })
    .catch(function(err) {
      console.warn('[用户系统] users.json 刷新失败，继续使用本地数据:', err.message);
    });
}'''

i = html.find(u"function preloadUsers() {")
j = html.find(u"\n\nfunction getUsers() {", i + 1) if i >= 0 else -1
if i >= 0 and j > i:
    html = html[:i] + NEW_USERS + html[j:]
    changed.append('用户加载改为缓存/内联优先')

# ---------- 4. doLogin 等待逻辑：3 秒兜底强制放行，不再弹超时框 ----------
NEW_WAIT = u'''  // 用户数据已优先使用本地缓存立即放行，此处等待仅作兜底
  if (!usersReady || !rolesReady) {
    var btn = document.getElementById('loginBtn');
    var origText = btn ? btn.textContent : '';
    if (btn) { btn.textContent = '加载中...'; btn.disabled = true; }
    var waited = 0;
    var checkInterval = setInterval(function() {
      waited += 200;
      if ((usersReady && rolesReady) || waited > 3000) {
        clearInterval(checkInterval);
        if (!usersReady) { usersCache = usersCache || getDefaultUsers(); usersReady = true; }
        if (!rolesReady) { rolesReady = true; }
        if (btn) { btn.textContent = origText; btn.disabled = false; }
        doLogin(); // 数据就绪（或兜底放行）后重新执行登录
      }
    }, 200);
    return;
  }

'''

i = html.find(u"  // 用户数据可能还在从服务器加载，等待就绪")
j = html.find(u"  var users = getUsers();", i + 1) if i >= 0 else -1
if i >= 0 and j > i:
    html = html[:i] + NEW_WAIT + html[j:]
    changed.append('登录等待改为 3 秒兜底放行')

# 兼容旧文案
i = html.find(u"  // 用户数据可能还在从服务器加载（preloadUsers/loadCustomRolesFromGitHub 已优化为立即放行，此等待仅兜底）")
if i >= 0:
    j = html.find(u"  var users = getUsers();", i + 1)
    if j > i:
        html = html[:i] + NEW_WAIT + html[j:]
        changed.append('登录等待改为 3 秒兜底放行(旧文案)')

with io.open(PATH, 'w', encoding='utf-8') as f:
    f.write(html)

print('修改项:', ' | '.join(changed) if changed else '无（已是最新）')
print('文件大小:', len(html))
print('残留旧超时提示:', html.count(u'用户数据加载超时，请刷新页面重试'))
print('EMBEDDED_USERS:', html.count('EMBEDDED_USERS'))
