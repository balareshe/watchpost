// Copyright (C) 2026 balareshe（摆烂人生） <https://github.com/balareshe/watchpost>. All rights reserved.
// Licensed under the Watchpost Non-Commercial Source License 1.0 (see LICENSE).
// 本项目禁止商业使用；分发须保留本声明与授权协议，并署名 Watchpost。
import { reactive } from "vue";
import { get, post } from "./api";

export const session = reactive({
  email: "",
  role: "",
  ready: false,
  authed: false
});

export const ROLE_LABEL = {
  admin: "管理员",
  maintainer: "维护人员",
  viewer: "只读"
};

export async function loadSession() {
  try {
    const me = await get("/api/auth/me");
    session.email = me.email || "";
    session.role = me.role || "viewer";
    session.authed = true;
  } catch {
    session.authed = false;
  } finally {
    session.ready = true;
  }
}

export async function login(email, code) {
  const res = await post("/api/auth/verify", { email, code });
  session.email = res.email || email;
  session.role = res.role || "viewer";
  session.authed = true;
  return res;
}

export async function logout() {
  try {
    await post("/api/auth/logout", {});
  } finally {
    session.authed = false;
    session.email = "";
    session.role = "";
  }
}

/** 管理员：全部权限（含用户管理） */
export const isAdmin = () => session.role === "admin";

/** 可写：管理员 + 维护人员（事件 / 公告 / 维护 / 节点） */
export const canWrite = () => session.role === "admin" || session.role === "maintainer";

/** 只读：只能看概览 */
export const isViewer = () => session.role === "viewer";

export const roleLabel = (role) => ROLE_LABEL[role] || role;
