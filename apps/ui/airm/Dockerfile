# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT

# ---- Dependencies ----
FROM node:26-alpine AS dependencies
WORKDIR /app

# Set-up corepack and pnpm
RUN npm install -g corepack@latest
RUN corepack enable pnpm

# Copy workspace-level files
COPY .npmrc package*.json pnpm-*.yaml tsconfig.base.json custom.d.ts ./
COPY airm/ ./airm/
COPY shared/ ./shared/

# Setup environment file
RUN mv airm/.env.local.example airm/.env.local

# Install dependencies
RUN pnpm install --frozen-lockfile

# ---- Build ----
FROM dependencies AS build
WORKDIR /app

ARG GITHUB_SHA_SHORT

# Copy full AIRM UI source
COPY airm/ ./airm/

# Build the AIRM application with Next.js
RUN export NEXT_PUBLIC_BUILD_VERSION="$(date +"%y%m%d")-${GITHUB_SHA_SHORT}" \
    && echo "Creating build $NEXT_PUBLIC_BUILD_VERSION" \
    && cd airm && pnpm build

# ---- Production ----
FROM node:26-alpine AS production
WORKDIR /app

# Install dumb-init for proper signal handling
RUN apk add --no-cache --no-check-certificate dumb-init

# Copy standalone output (self-contained with minimal node_modules)
COPY --chown=node:node --from=build /app/airm/.next/standalone /app
COPY --chown=node:node --from=build /app/airm/.next/static /app/airm/.next/static
COPY --chown=node:node --from=build /app/airm/public /app/airm/public
COPY --chown=node:node --from=build /app/airm/next-i18next.config.js /app/airm/next-i18next.config.js
COPY --chown=node:node --from=build /app/shared/components/locales /app/shared/components/locales
COPY --chown=node:node --from=build /app/shared/scripts /app/shared/scripts

# Switch to non-root user
USER node

ARG NODE_ENV=production
ENV NODE_ENV=$NODE_ENV

# Expose the port the app will run on
ARG PORT=8000
ENV PORT=$PORT
EXPOSE $PORT

# Set environment variable for Next.js
ENV HOSTNAME="0.0.0.0"

# Start the application with dumb-init for proper signal handling
CMD ["dumb-init", "node", "airm/server.js"]
