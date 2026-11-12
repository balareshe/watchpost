import { createRouter, createWebHashHistory } from "vue-router";
import Dashboard from "./views/Dashboard.vue";
import Incidents from "./views/Incidents.vue";
import Tickets from "./views/Tickets.vue";
import TicketDetail from "./views/TicketDetail.vue";
import Announcements from "./views/Announcements.vue";
import Maintenance from "./views/Maintenance.vue";
import Nodes from "./views/Nodes.vue";
import Users from "./views/Users.vue";
import Settings from "./views/Settings.vue";
import SiteSettings from "./views/SiteSettings.vue";
import Notifications from "./views/Notifications.vue";

const routes = [
  { path: "/", name: "dash", component: Dashboard, meta: { title: "概览" } },
  { path: "/tickets", name: "tickets", component: Tickets, meta: { title: "工单" } },
  { path: "/tickets/:id", name: "ticket", component: TicketDetail, meta: { title: "工单详情" } },
  { path: "/incidents", name: "incidents", component: Incidents, meta: { title: "事件" } },
  { path: "/announcements", name: "announcements", component: Announcements, meta: { title: "公告" } },
  { path: "/maintenance", name: "maintenance", component: Maintenance, meta: { title: "维护" } },
  { path: "/nodes", name: "nodes", component: Nodes, meta: { title: "节点" } },
  { path: "/users", name: "users", component: Users, meta: { title: "用户", adminOnly: true } },
  { path: "/site", name: "site", component: SiteSettings, meta: { title: "系统设置", adminOnly: true } },
  { path: "/notifications", name: "notifications", component: Notifications, meta: { title: "通知", adminOnly: true } },
  { path: "/settings", name: "settings", component: Settings, meta: { title: "设置" } },
  { path: "/:pathMatch(.*)*", redirect: "/" }
];

export default createRouter({
  history: createWebHashHistory(),
  routes
});
