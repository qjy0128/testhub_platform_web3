export interface RequestModel {
  method: string
  baseURL: string
  path: string
  query: QueryParam[]
  headers: Header[]
  body: Body
  auth?: Auth
  timeout?: number
}

export interface QueryParam {
  key: string
  value: string
  enabled: boolean
}

export interface Header {
  key: string
  value: string
  enabled: boolean
}

export interface Body {
  mode: 'none' | 'raw' | 'json' | 'formdata' | 'urlencoded' | 'binary'
  raw?: string
  json?: string
  formdata?: FormField[]
  urlencoded?: FormField[]
  binary?: File
}

export interface FormField {
  key: string
  value: string
  type: 'text' | 'file'
  enabled: boolean
}

export interface Auth {
  type: 'none' | 'basic' | 'bearer' | 'api_key'
  username?: string
  password?: string
  token?: string
  key?: string
  value?: string
  addTo?: 'header' | 'query'
}

function tokenizeCurlCommand(command: string): string[] {
  const tokens: string[] = []
  let current = ''
  let quote: '"' | "'" | null = null
  let escaped = false

  for (const char of command.trim()) {
    if (escaped) {
      if (char !== '\n' && char !== '\r') {
        current += char
      }
      escaped = false
      continue
    }

    if (char === '\\' && quote !== "'") {
      escaped = true
      continue
    }

    if (quote) {
      if (char === quote) {
        quote = null
      } else {
        current += char
      }
      continue
    }

    if (char === '"' || char === "'") {
      quote = char
      continue
    }

    if (/\s/.test(char)) {
      if (current) {
        tokens.push(current)
        current = ''
      }
      continue
    }

    current += char
  }

  if (escaped) {
    current += '\\'
  }
  if (quote) {
    throw new Error('cURL 命令存在未闭合的引号')
  }
  if (current) {
    tokens.push(current)
  }

  return tokens
}

function splitOption(token: string): [string, string | undefined] {
  const equalIndex = token.indexOf('=')
  if (token.startsWith('--') && equalIndex > -1) {
    return [token.slice(0, equalIndex), token.slice(equalIndex + 1)]
  }
  if (token.startsWith('-X') && token.length > 2) {
    return ['-X', token.slice(2)]
  }
  if (token.startsWith('-H') && token.length > 2) {
    return ['-H', token.slice(2)]
  }
  if (token.startsWith('-d') && token.length > 2) {
    return ['-d', token.slice(2)]
  }
  if (token.startsWith('-F') && token.length > 2) {
    return ['-F', token.slice(2)]
  }
  return [token, undefined]
}

function normalizeUrl(value: string): URL {
  const raw = value.trim()
  return new URL(/^https?:\/\//i.test(raw) ? raw : `http://${raw}`)
}

function parseHeader(value: string): Header | null {
  const colonIndex = value.indexOf(':')
  if (colonIndex <= 0) {
    return null
  }
  return {
    key: value.slice(0, colonIndex).trim(),
    value: value.slice(colonIndex + 1).trim(),
    enabled: true
  }
}

function parsePairs(value: string): FormField[] {
  return value
    .split('&')
    .filter(Boolean)
    .map(item => {
      const equalIndex = item.indexOf('=')
      if (equalIndex === -1) {
        return { key: decodeURIComponent(item), value: '', type: 'text', enabled: true }
      }
      return {
        key: decodeURIComponent(item.slice(0, equalIndex)),
        value: decodeURIComponent(item.slice(equalIndex + 1)),
        type: 'text',
        enabled: true
      }
    })
}

function parseFormField(value: string): FormField | null {
  const equalIndex = value.indexOf('=')
  if (equalIndex <= 0) {
    return null
  }
  const key = value.slice(0, equalIndex)
  const rawValue = value.slice(equalIndex + 1)
  return {
    key,
    value: rawValue.startsWith('@') ? rawValue.slice(1) : rawValue,
    type: rawValue.startsWith('@') ? 'file' : 'text',
    enabled: true
  }
}

export class RequestModelParser {
  static async parseCurl(curlCommand: string): Promise<RequestModel> {
    try {
      const tokens = tokenizeCurlCommand(curlCommand)
      if (!tokens.length || !/curl(?:\.exe)?$/i.test(tokens[0])) {
        throw new Error('命令必须以 curl 开头')
      }

      let method = 'GET'
      let urlValue = ''
      const headers: Header[] = []
      const dataChunks: string[] = []
      const formFields: FormField[] = []
      let forceUrlEncoded = false

      const readValue = (index: number, inlineValue?: string) => {
        if (inlineValue !== undefined) {
          return { value: inlineValue, nextIndex: index }
        }
        const value = tokens[index + 1]
        if (value === undefined) {
          throw new Error(`选项 ${tokens[index]} 缺少参数`)
        }
        return { value, nextIndex: index + 1 }
      }

      for (let i = 1; i < tokens.length; i += 1) {
        const token = tokens[i]
        const [option, inlineValue] = splitOption(token)

        if (!option.startsWith('-')) {
          urlValue = urlValue || option
          continue
        }

        if (option === '-X' || option === '--request') {
          const result = readValue(i, inlineValue)
          method = result.value.toUpperCase()
          i = result.nextIndex
        } else if (option === '-H' || option === '--header') {
          const result = readValue(i, inlineValue)
          const header = parseHeader(result.value)
          if (header) {
            headers.push(header)
          }
          i = result.nextIndex
        } else if (option === '-A' || option === '--user-agent') {
          const result = readValue(i, inlineValue)
          headers.push({ key: 'User-Agent', value: result.value, enabled: true })
          i = result.nextIndex
        } else if (option === '-b' || option === '--cookie' || option === '--cookie-jar') {
          const result = readValue(i, inlineValue)
          headers.push({ key: 'Cookie', value: result.value, enabled: true })
          i = result.nextIndex
        } else if (option === '-u' || option === '--user') {
          const result = readValue(i, inlineValue)
          headers.push({ key: 'Authorization', value: `Basic ${btoa(result.value)}`, enabled: true })
          i = result.nextIndex
        } else if (
          option === '-d' ||
          option === '--data' ||
          option === '--data-raw' ||
          option === '--data-binary' ||
          option === '--data-ascii' ||
          option === '--data-urlencode'
        ) {
          const result = readValue(i, inlineValue)
          dataChunks.push(result.value)
          forceUrlEncoded = forceUrlEncoded || option === '--data-urlencode'
          if (method === 'GET') {
            method = 'POST'
          }
          i = result.nextIndex
        } else if (option === '-F' || option === '--form' || option === '--form-string') {
          const result = readValue(i, inlineValue)
          const field = parseFormField(result.value)
          if (field) {
            formFields.push(field)
          }
          if (method === 'GET') {
            method = 'POST'
          }
          i = result.nextIndex
        } else if (option === '--url') {
          const result = readValue(i, inlineValue)
          urlValue = result.value
          i = result.nextIndex
        } else if (option === '-I' || option === '--head') {
          method = 'HEAD'
        }
      }

      if (!urlValue) {
        throw new Error('未找到请求 URL')
      }

      const url = normalizeUrl(urlValue)
      const baseURL = `${url.protocol}//${url.host}`
      const path = url.pathname
      const query: QueryParam[] = []

      url.searchParams.forEach((value, key) => {
        query.push({ key, value, enabled: true })
      })

      const body: Body = { mode: 'none' }
      const contentType = headers.find(h => h.key.toLowerCase() === 'content-type')?.value?.toLowerCase() || ''

      if (formFields.length) {
        body.mode = 'formdata'
        body.formdata = formFields
      } else if (dataChunks.length) {
        const rawBody = dataChunks.join('&')
        if (contentType.includes('application/json') || /^[\[{]/.test(rawBody.trim())) {
          body.mode = 'json'
          body.json = rawBody
        } else if (forceUrlEncoded || contentType.includes('application/x-www-form-urlencoded')) {
          body.mode = 'urlencoded'
          body.urlencoded = parsePairs(rawBody)
        } else {
          body.mode = 'raw'
          body.raw = rawBody
        }
      }

      return {
        method,
        baseURL,
        path,
        query,
        headers,
        body,
        auth: RequestModelParser.parseAuth(headers),
        timeout: 30000
      }
    } catch (error: any) {
      console.error('Failed to parse cURL command:', error)
      console.error('cURL command:', curlCommand)
      const errorMessage = error?.message || error?.toString() || 'Unknown error'
      throw new Error(`cURL命令解析失败: ${errorMessage}，请检查命令格式`)
    }
  }
  
  static parseAuth(headers: Header[]): Auth | undefined {
    const authHeader = headers.find(h => h.key.toLowerCase() === 'authorization')
    if (authHeader) {
      const value = authHeader.value
      
      if (value.startsWith('Bearer ')) {
        return {
          type: 'bearer',
          token: value.substring(7)
        }
      }
      
      if (value.startsWith('Basic ')) {
        try {
          const decoded = atob(value.substring(6))
          const [username, password] = decoded.split(':')
          return {
            type: 'basic',
            username,
            password
          }
        } catch {
          return undefined
        }
      }
    }
    
    return undefined
  }
  
  static toCurl(model: RequestModel): string {
    let curl = `curl -X ${model.method}`
    
    let url: URL
    if (model.baseURL && model.path) {
      url = new URL(model.baseURL + model.path)
    } else if (model.baseURL) {
      url = new URL(model.baseURL)
    } else if (model.path) {
      url = new URL(model.path)
    } else {
      throw new Error('Invalid URL: both baseURL and path are empty')
    }
    
    model.query.forEach(param => {
      if (param.enabled && param.key) {
        url.searchParams.append(param.key, param.value)
      }
    })
    curl += ` '${url.toString()}'`
    
    model.headers.forEach(header => {
      if (header.enabled && header.key) {
        curl += ` -H '${header.key}: ${header.value}'`
      }
    })
    
    if (model.body.mode !== 'none' && model.body.raw) {
      curl += ` -d '${model.body.raw}'`
    }
    
    if (model.timeout) {
      curl += ` --max-time ${model.timeout / 1000}`
    }
    
    return curl
  }
  
  static toFormData(model: RequestModel): FormData {
    const formData = new FormData()
    
    if (model.body.mode === 'formdata' && model.body.formdata) {
      model.body.formdata.forEach(field => {
        if (field.enabled && field.key) {
          if (field.type === 'file' && field.value) {
            formData.append(field.key, field.value as any)
          } else {
            formData.append(field.key, field.value)
          }
        }
      })
    }
    
    return formData
  }
  
  static toURLSearchParams(model: RequestModel): URLSearchParams {
    const params = new URLSearchParams()
    
    if (model.body.mode === 'urlencoded' && model.body.urlencoded) {
      model.body.urlencoded.forEach(field => {
        if (field.enabled && field.key) {
          params.append(field.key, field.value)
        }
      })
    }
    
    return params
  }
}
