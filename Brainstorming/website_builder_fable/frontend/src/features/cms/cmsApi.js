// OWNED BY: frontend-cms agent (src/features/cms/**).
// Thin wrappers over the shared api client for the CMS endpoints (docs/CONTRACTS.md 1.3, 1.4).

import { apiGet, apiPost, apiPut, apiDelete, uploadFile } from '../../api/client.js'

const base = (projectId) => `/api/projects/${projectId}`

// Project (read-only, for the breadcrumb)
export function getProject(projectId) {
  return apiGet(base(projectId))
}

// Collections
export function listCollections(projectId) {
  return apiGet(`${base(projectId)}/collections`)
}

export function createCollection(projectId, data) {
  return apiPost(`${base(projectId)}/collections`, data)
}

export function getCollection(projectId, collectionId) {
  return apiGet(`${base(projectId)}/collections/${collectionId}`)
}

export function updateCollection(projectId, collectionId, data) {
  return apiPut(`${base(projectId)}/collections/${collectionId}`, data)
}

export function deleteCollection(projectId, collectionId) {
  return apiDelete(`${base(projectId)}/collections/${collectionId}`)
}

// Entries
export function listEntries(projectId, collectionId, limit = 50, offset = 0) {
  return apiGet(
    `${base(projectId)}/collections/${collectionId}/entries?limit=${limit}&offset=${offset}`
  )
}

export function createEntry(projectId, collectionId, data) {
  return apiPost(`${base(projectId)}/collections/${collectionId}/entries`, { data })
}

export function getEntry(projectId, collectionId, entryId) {
  return apiGet(`${base(projectId)}/collections/${collectionId}/entries/${entryId}`)
}

export function updateEntry(projectId, collectionId, entryId, data) {
  return apiPut(`${base(projectId)}/collections/${collectionId}/entries/${entryId}`, { data })
}

export function deleteEntry(projectId, collectionId, entryId) {
  return apiDelete(`${base(projectId)}/collections/${collectionId}/entries/${entryId}`)
}

// Assets
export function listAssets(projectId) {
  return apiGet(`${base(projectId)}/assets`)
}

export function uploadAsset(projectId, file) {
  return uploadFile(`${base(projectId)}/assets`, file)
}

export function deleteAsset(projectId, assetId) {
  return apiDelete(`${base(projectId)}/assets/${assetId}`)
}
