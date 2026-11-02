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
COPY aiwb/ ./aiwb/
COPY shared/ ./shared/

# Setup environment file
RUN mv aiwb/.env.local.example aiwb/.env.local

# Install dependencies
RUN pnpm install --frozen-lockfile

# ---- Build ----
FROM dependencies AS build
WORKDIR /app


ARG GITHUB_SHA_SHORT

# Copy full AIWB UI source
COPY aiwb/ ./aiwb/

# Build the AIWB application with Next.js
RUN export NEXT_PUBLIC_BUILD_VERSION="$(date +"%y%m%d")-${GITHUB_SHA_SHORT}" \
    && echo "Creating build $NEXT_PUBLIC_BUILD_VERSION" \
    && cd aiwb && pnpm build

# ---- Production ----
FROM node:26-alpine AS production
WORKDIR /app


# Install dumb-init for proper signal handling
RUN apk add --no-cache --no-check-certificate dumb-init

# Copy standalone output (self-contained with minimal node_modules)
COPY --chown=node:node --from=build /app/aiwb/.next/standalone /app
COPY --chown=node:node --from=build /app/aiwb/.next/static /app/aiwb/.next/static
COPY --chown=node:node --from=build /app/aiwb/public /app/aiwb/public
COPY --chown=node:node --from=build /app/aiwb/next-i18next.config.js /app/aiwb/next-i18next.config.js
COPY --chown=node:node --from=build /app/shared/components/locales /app/shared/components/locales
COPY --chown=node:node --from=build /app/shared/scripts /app/shared/scripts


# Accept runtime args for dynamic config
ARG STANDALONE_MODE
ARG DEFAULT_NAMESPACE
ARG API_KEYS_MANAGEMENT_ENABLED

# Switch to non-root user
USER node

ARG NODE_ENV=production
ENV NODE_ENV=$NODE_ENV

# Set runtime environment variables for Next.js
ENV STANDALONE_MODE=${STANDALONE_MODE}
ENV DEFAULT_NAMESPACE=${DEFAULT_NAMESPACE}
ENV API_KEYS_MANAGEMENT_ENABLED=${API_KEYS_MANAGEMENT_ENABLED}

# Expose the port the app will run on
ARG PORT=8000
ENV PORT=$PORT
EXPOSE $PORT

# Set environment variable for Next.js
ENV HOSTNAME="0.0.0.0"

# Start the application with dumb-init for proper signal handling
CMD ["dumb-init", "node", "aiwb/server.js"]
