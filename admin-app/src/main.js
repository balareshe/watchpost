// Copyright (C) 2026 balareshe（摆烂人生） <https://github.com/balareshe/watchpost>. All rights reserved.
// Licensed under the Watchpost Non-Commercial Source License 1.0 (see LICENSE).
// 本项目禁止商业使用；分发须保留本声明与授权协议，并署名 Watchpost。
import { createApp } from "vue";
import App from "./App.vue";
import router from "./router";
import "./style.css";

createApp(App).use(router).mount("#app");
