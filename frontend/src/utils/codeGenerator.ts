import type { Body, Header, RequestModel } from './requestModel'

export interface CodeTemplate {
  language: string
  extension: string
  generator: (curlCommand: string) => string
}

interface RequestInfo {
  method: string
  url: string
  headers: Record<string, string>
  body: string
  bodyMode: Body['mode']
}

export class CodeGenerator {
  private static languageMap: Record<string, string> = {
    javascript: 'javascript',
    python: 'python',
    java: 'java',
    node: 'node',
    curl: 'http',
    php: 'php',
    go: 'go',
    csharp: 'csharp',
    ruby: 'ruby',
    swift: 'swift',
    kotlin: 'kotlin',
    rust: 'rust',
    dart: 'dart',
    objective_c: 'objc',
    powershell: 'powershell',
    matlab: 'matlab',
    r: 'r',
    ansible: 'ansible',
    c: 'c',
    cfml: 'cfml',
    clojure: 'clojure',
    elixir: 'elixir',
    http: 'http',
    httpie: 'httpie',
    julia: 'julia',
    lua: 'lua',
    ocaml: 'ocaml',
    perl: 'perl',
    wget: 'wget'
  }

  private static languageLabels: Record<string, string> = {
    javascript: 'JavaScript',
    python: 'Python',
    java: 'Java',
    node: 'Node.js',
    curl: 'cURL',
    php: 'PHP',
    go: 'Go',
    csharp: 'C#',
    ruby: 'Ruby',
    swift: 'Swift',
    kotlin: 'Kotlin',
    rust: 'Rust',
    dart: 'Dart',
    objective_c: 'Objective-C',
    powershell: 'PowerShell',
    matlab: 'MATLAB',
    r: 'R',
    ansible: 'Ansible',
    c: 'C',
    cfml: 'CFML',
    clojure: 'Clojure',
    elixir: 'Elixir',
    http: 'HTTP',
    httpie: 'HTTPie',
    julia: 'Julia',
    lua: 'Lua',
    ocaml: 'OCaml',
    perl: 'Perl',
    wget: 'Wget'
  }

  private static languageExtensions: Record<string, string> = {
    javascript: 'js',
    python: 'py',
    java: 'java',
    node: 'js',
    curl: 'sh',
    php: 'php',
    go: 'go',
    csharp: 'cs',
    ruby: 'rb',
    swift: 'swift',
    kotlin: 'kt',
    rust: 'rs',
    dart: 'dart',
    objective_c: 'm',
    powershell: 'ps1',
    matlab: 'm',
    r: 'r',
    ansible: 'yml',
    c: 'c',
    cfml: 'cfm',
    clojure: 'clj',
    elixir: 'ex',
    http: 'http',
    httpie: 'http',
    julia: 'jl',
    lua: 'lua',
    ocaml: 'ml',
    perl: 'pl',
    wget: 'sh'
  }

  static async generateCode(model: RequestModel, language: string): Promise<string> {
    const curlCommand = this.buildCurlCommand(model)

    if (language === 'curl') {
      return curlCommand
    }

    const mappedLanguage = this.languageMap[language] || language
    const info = this.toRequestInfo(model)

    try {
      switch (mappedLanguage) {
        case 'javascript':
        case 'node':
          return this.generateFetch(info)
        case 'python':
          return this.generatePython(info)
        case 'java':
          return this.generateJava(info)
        case 'http':
          return this.generateHttp(info)
        case 'php':
          return this.generatePhp(info)
        case 'go':
          return this.generateGo(info)
        case 'csharp':
          return this.generateCSharp(info)
        case 'ruby':
          return this.generateRuby(info)
        case 'swift':
          return this.generateSwift(info)
        case 'kotlin':
          return this.generateKotlin(info)
        case 'rust':
          return this.generateRust(info)
        case 'dart':
          return this.generateDart(info)
        case 'objc':
          return this.generateObjectiveC(info)
        case 'powershell':
          return this.generatePowerShell(info)
        case 'matlab':
          return this.generateMatlab(info)
        case 'r':
          return this.generateR(info)
        case 'ansible':
          return this.generateAnsible(info)
        case 'c':
          return this.generateC(info)
        case 'cfml':
          return this.generateCfml(info)
        case 'clojure':
          return this.generateClojure(info)
        case 'elixir':
          return this.generateElixir(info)
        case 'httpie':
          return this.generateHttpie(info)
        case 'julia':
          return this.generateJulia(info)
        case 'lua':
          return this.generateLua(info)
        case 'ocaml':
          return this.generateOcaml(info)
        case 'perl':
          return this.generatePerl(info)
        case 'wget':
          return this.generateWget(info)
        default:
          return this.generateFallback(language, curlCommand)
      }
    } catch (error) {
      console.error('Error generating code:', error)
      return `// Error generating code: ${error}`
    }
  }

  private static toRequestInfo(model: RequestModel): RequestInfo {
    return {
      method: model.method.toUpperCase(),
      url: this.buildUrl(model),
      headers: this.enabledHeaders(model.headers),
      body: this.bodyValue(model.body),
      bodyMode: model.body.mode
    }
  }

  private static buildCurlCommand(model: RequestModel): string {
    const parts = ['curl', '-X', model.method.toUpperCase()]

    model.headers
      .filter(header => header.enabled && header.key)
      .forEach(header => {
        parts.push('-H', this.shellQuote(`${header.key}: ${header.value}`))
      })

    if (model.body.mode === 'formdata' && model.body.formdata) {
      model.body.formdata
        .filter(field => field.enabled && field.key)
        .forEach(field => {
          const value = field.type === 'file' ? `@${field.value}` : field.value
          parts.push('-F', this.shellQuote(`${field.key}=${value}`))
        })
    } else if (model.body.mode === 'urlencoded' && model.body.urlencoded) {
      model.body.urlencoded
        .filter(field => field.enabled && field.key)
        .forEach(field => {
          parts.push('--data-urlencode', this.shellQuote(`${field.key}=${field.value}`))
        })
    } else {
      const body = this.bodyValue(model.body)
      if (body) {
        parts.push('-d', this.shellQuote(body))
      }
    }

    parts.push(this.shellQuote(this.buildUrl(model)))
    return parts.join(' ')
  }

  private static buildUrl(model: RequestModel): string {
    try {
      const url = new URL(model.baseURL + model.path)
      model.query.forEach(param => {
        if (param.enabled && param.key) {
          url.searchParams.append(param.key, param.value)
        }
      })
      return url.toString()
    } catch (error) {
      console.error('Error building URL:', error, { baseURL: model.baseURL, path: model.path })
      return model.baseURL + model.path
    }
  }

  private static enabledHeaders(headers: Header[]): Record<string, string> {
    return headers
      .filter(header => header.enabled && header.key)
      .reduce<Record<string, string>>((result, header) => {
        result[header.key] = header.value
        return result
      }, {})
  }

  private static bodyValue(body: Body): string {
    if (body.mode === 'none') {
      return ''
    }
    if (body.mode === 'json') {
      return body.json || body.raw || ''
    }
    if (body.mode === 'raw' || body.mode === 'binary') {
      return body.raw || body.json || ''
    }
    if (body.mode === 'urlencoded' && body.urlencoded) {
      return body.urlencoded
        .filter(field => field.enabled && field.key)
        .map(field => `${encodeURIComponent(field.key)}=${encodeURIComponent(field.value)}`)
        .join('&')
    }
    if (body.mode === 'formdata' && body.formdata) {
      return body.formdata
        .filter(field => field.enabled && field.key)
        .map(field => `${field.key}=${field.type === 'file' ? `@${field.value}` : field.value}`)
        .join('&')
    }
    return ''
  }

  private static shellQuote(value: string): string {
    return `'${value.replace(/'/g, "'\\''")}'`
  }

  private static doubleQuote(value: string): string {
    return value.replace(/\\/g, '\\\\').replace(/"/g, '\\"')
  }

  private static jsonString(value: string): string {
    return JSON.stringify(value)
  }

  private static headersObject(info: RequestInfo): string {
    return JSON.stringify(info.headers, null, 2)
  }

  private static generateFetch(info: RequestInfo): string {
    const options: Record<string, unknown> = {
      method: info.method,
      headers: info.headers
    }
    if (info.body) {
      options.body = info.body
    }
    return `const response = await fetch(${this.jsonString(info.url)}, ${JSON.stringify(options, null, 2)})
const data = await response.text()
console.log(data)`
  }

  private static generatePython(info: RequestInfo): string {
    const bodyArg = info.body ? `,\n    data=${this.jsonString(info.body)}` : ''
    return `import requests

response = requests.request(
    ${this.jsonString(info.method)},
    ${this.jsonString(info.url)},
    headers=${JSON.stringify(info.headers, null, 4)}${bodyArg}
)
print(response.text)`
  }

  private static generateJava(info: RequestInfo): string {
    const headerLines = Object.entries(info.headers)
      .map(([key, value]) => `            .header("${this.doubleQuote(key)}", "${this.doubleQuote(value)}")`)
      .join('\n')
    const bodyPublisher = info.body
      ? `HttpRequest.BodyPublishers.ofString(${this.jsonString(info.body)})`
      : 'HttpRequest.BodyPublishers.noBody()'
    return `import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;

HttpClient client = HttpClient.newHttpClient();
HttpRequest request = HttpRequest.newBuilder()
            .uri(URI.create(${this.jsonString(info.url)}))
${headerLines ? `${headerLines}\n` : ''}            .method(${this.jsonString(info.method)}, ${bodyPublisher})
            .build();

HttpResponse<String> response = client.send(request, HttpResponse.BodyHandlers.ofString());
System.out.println(response.body());`
  }

  private static generateHttp(info: RequestInfo): string {
    const url = new URL(info.url)
    const headers = [`Host: ${url.host}`]
      .concat(Object.entries(info.headers).map(([key, value]) => `${key}: ${value}`))
      .join('\n')
    return `${info.method} ${url.pathname}${url.search} HTTP/1.1
${headers}${info.body ? `\n\n${info.body}` : ''}`
  }

  private static generatePhp(info: RequestInfo): string {
    const headers = Object.entries(info.headers).map(([key, value]) => `${key}: ${value}`)
    return `<?php
$ch = curl_init(${this.jsonString(info.url)});
curl_setopt($ch, CURLOPT_CUSTOMREQUEST, ${this.jsonString(info.method)});
curl_setopt($ch, CURLOPT_RETURNTRANSFER, true);
${headers.length ? `curl_setopt($ch, CURLOPT_HTTPHEADER, ${JSON.stringify(headers, null, 2)});\n` : ''}${info.body ? `curl_setopt($ch, CURLOPT_POSTFIELDS, ${this.jsonString(info.body)});\n` : ''}$response = curl_exec($ch);
curl_close($ch);
echo $response;`
  }

  private static generateGo(info: RequestInfo): string {
    const headerLines = Object.entries(info.headers)
      .map(([key, value]) => `req.Header.Set(${this.jsonString(key)}, ${this.jsonString(value)})`)
      .join('\n')
    return `package main

import (
  "fmt"
  "io"
  "net/http"
  "strings"
)

func main() {
  body := strings.NewReader(${this.jsonString(info.body)})
  req, _ := http.NewRequest(${this.jsonString(info.method)}, ${this.jsonString(info.url)}, body)
${headerLines ? `  ${headerLines.replace(/\n/g, '\n  ')}\n` : ''}  resp, _ := http.DefaultClient.Do(req)
  defer resp.Body.Close()
  bytes, _ := io.ReadAll(resp.Body)
  fmt.Println(string(bytes))
}`
  }

  private static generateCSharp(info: RequestInfo): string {
    const headers = Object.entries(info.headers)
      .map(([key, value]) => `request.Headers.TryAddWithoutValidation(${this.jsonString(key)}, ${this.jsonString(value)});`)
      .join('\n')
    return `using System.Net.Http;

using var client = new HttpClient();
using var request = new HttpRequestMessage(new HttpMethod(${this.jsonString(info.method)}), ${this.jsonString(info.url)});
${headers}${info.body ? `\nrequest.Content = new StringContent(${this.jsonString(info.body)});` : ''}
using var response = await client.SendAsync(request);
Console.WriteLine(await response.Content.ReadAsStringAsync());`
  }

  private static generateRuby(info: RequestInfo): string {
    return `require 'net/http'

uri = URI(${this.jsonString(info.url)})
request = Net::HTTP::${info.method.charAt(0)}${info.method.slice(1).toLowerCase()}.new(uri)
${Object.entries(info.headers).map(([key, value]) => `request[${this.jsonString(key)}] = ${this.jsonString(value)}`).join('\n')}${info.body ? `\nrequest.body = ${this.jsonString(info.body)}` : ''}
response = Net::HTTP.start(uri.hostname, uri.port, use_ssl: uri.scheme == 'https') { |http| http.request(request) }
puts response.body`
  }

  private static generateSwift(info: RequestInfo): string {
    return `import Foundation

var request = URLRequest(url: URL(string: ${this.jsonString(info.url)})!)
request.httpMethod = ${this.jsonString(info.method)}
${Object.entries(info.headers).map(([key, value]) => `request.setValue(${this.jsonString(value)}, forHTTPHeaderField: ${this.jsonString(key)})`).join('\n')}${info.body ? `\nrequest.httpBody = ${this.jsonString(info.body)}.data(using: .utf8)` : ''}
URLSession.shared.dataTask(with: request) { data, _, _ in
    print(String(data: data ?? Data(), encoding: .utf8) ?? "")
}.resume()`
  }

  private static generateKotlin(info: RequestInfo): string {
    return `val client = okhttp3.OkHttpClient()
val body = ${info.body ? `okhttp3.RequestBody.create(null, ${this.jsonString(info.body)})` : 'null'}
val request = okhttp3.Request.Builder()
    .url(${this.jsonString(info.url)})
${Object.entries(info.headers).map(([key, value]) => `    .addHeader(${this.jsonString(key)}, ${this.jsonString(value)})`).join('\n')}
    .method(${this.jsonString(info.method)}, body)
    .build()
val response = client.newCall(request).execute()
println(response.body?.string())`
  }

  private static generateRust(info: RequestInfo): string {
    return `let client = reqwest::Client::new();
let response = client
    .request(reqwest::Method::${info.method}, ${this.jsonString(info.url)})
${Object.entries(info.headers).map(([key, value]) => `    .header(${this.jsonString(key)}, ${this.jsonString(value)})`).join('\n')}${info.body ? `\n    .body(${this.jsonString(info.body)})` : ''}
    .send()
    .await?;
println!("{}", response.text().await?);`
  }

  private static generateDart(info: RequestInfo): string {
    return `import 'package:http/http.dart' as http;

final response = await http.Request(${this.jsonString(info.method)}, Uri.parse(${this.jsonString(info.url)}))
  ..headers.addAll(${JSON.stringify(info.headers)})
${info.body ? `  ..body = ${this.jsonString(info.body)}\n` : ''};
print((await response.send()).statusCode);`
  }

  private static generateObjectiveC(info: RequestInfo): string {
    return `NSMutableURLRequest *request = [NSMutableURLRequest requestWithURL:[NSURL URLWithString:@${this.jsonString(info.url)}]];
[request setHTTPMethod:@${this.jsonString(info.method)}];
${Object.entries(info.headers).map(([key, value]) => `[request setValue:@${this.jsonString(value)} forHTTPHeaderField:@${this.jsonString(key)}];`).join('\n')}${info.body ? `\n[request setHTTPBody:[@${this.jsonString(info.body)} dataUsingEncoding:NSUTF8StringEncoding]];` : ''}`
  }

  private static generatePowerShell(info: RequestInfo): string {
    const headers = Object.entries(info.headers)
      .map(([key, value]) => `  ${this.jsonString(key)} = ${this.jsonString(value)}`)
      .join('\n')
    return `$headers = @{
${headers}
}
Invoke-WebRequest -Uri ${this.jsonString(info.url)} -Method ${info.method} -Headers $headers${info.body ? ` -Body ${this.jsonString(info.body)}` : ''}`
  }

  private static generateMatlab(info: RequestInfo): string {
    return `options = weboptions('RequestMethod', '${info.method.toLowerCase()}');
response = webread(${this.jsonString(info.url)}, options);`
  }

  private static generateR(info: RequestInfo): string {
    return `library(httr)

response <- VERB(${this.jsonString(info.method)}, ${this.jsonString(info.url)}, add_headers(.headers = ${JSON.stringify(info.headers)})${info.body ? `, body = ${this.jsonString(info.body)}` : ''})
content(response, "text")`
  }

  private static generateAnsible(info: RequestInfo): string {
    return `- name: HTTP request
  uri:
    url: ${info.url}
    method: ${info.method}
    headers: ${JSON.stringify(info.headers)}
${info.body ? `    body: ${info.body}\n` : ''}    return_content: true`
  }

  private static generateC(info: RequestInfo): string {
    return `CURL *curl = curl_easy_init();
curl_easy_setopt(curl, CURLOPT_URL, ${this.jsonString(info.url)});
curl_easy_setopt(curl, CURLOPT_CUSTOMREQUEST, ${this.jsonString(info.method)});
${info.body ? `curl_easy_setopt(curl, CURLOPT_POSTFIELDS, ${this.jsonString(info.body)});\n` : ''}curl_easy_perform(curl);
curl_easy_cleanup(curl);`
  }

  private static generateCfml(info: RequestInfo): string {
    return `<cfhttp url=${this.jsonString(info.url)} method=${this.jsonString(info.method)}>
${Object.entries(info.headers).map(([key, value]) => `  <cfhttpparam type="header" name=${this.jsonString(key)} value=${this.jsonString(value)}>`).join('\n')}${info.body ? `\n  <cfhttpparam type="body" value=${this.jsonString(info.body)}>` : ''}
</cfhttp>`
  }

  private static generateClojure(info: RequestInfo): string {
    return `(require '[clj-http.client :as client])
(client/request {:method :${info.method.toLowerCase()}
                 :url ${this.jsonString(info.url)}
                 :headers ${JSON.stringify(info.headers)}${info.body ? `\n                 :body ${this.jsonString(info.body)}` : ''}})`
  }

  private static generateElixir(info: RequestInfo): string {
    return `Req.request!(method: :${info.method.toLowerCase()}, url: ${this.jsonString(info.url)}, headers: ${JSON.stringify(info.headers)}${info.body ? `, body: ${this.jsonString(info.body)}` : ''})`
  }

  private static generateHttpie(info: RequestInfo): string {
    const headers = Object.entries(info.headers)
      .map(([key, value]) => `${this.shellQuote(`${key}:${value}`)}`)
      .join(' ')
    return `http ${info.method} ${this.shellQuote(info.url)} ${headers}${info.body ? ` ${this.shellQuote(info.body)}` : ''}`
  }

  private static generateJulia(info: RequestInfo): string {
    return `using HTTP

response = HTTP.request(${this.jsonString(info.method)}, ${this.jsonString(info.url)}, ${JSON.stringify(info.headers)}${info.body ? `, body=${this.jsonString(info.body)}` : ''})
println(String(response.body))`
  }

  private static generateLua(info: RequestInfo): string {
    return `local http = require("socket.http")
local response = http.request(${this.jsonString(info.url)}${info.body ? `, ${this.jsonString(info.body)}` : ''})
print(response)`
  }

  private static generateOcaml(info: RequestInfo): string {
    return `Cohttp_lwt_unix.Client.call \`${info.method} (Uri.of_string ${this.jsonString(info.url)})`
  }

  private static generatePerl(info: RequestInfo): string {
    return `use HTTP::Tiny;

my $response = HTTP::Tiny->new->request(${this.jsonString(info.method)}, ${this.jsonString(info.url)}, {
  headers => ${JSON.stringify(info.headers)}${info.body ? `,\n  content => ${this.jsonString(info.body)}` : ''}
});
print $response->{content};`
  }

  private static generateWget(info: RequestInfo): string {
    const headers = Object.entries(info.headers)
      .map(([key, value]) => `--header=${this.shellQuote(`${key}: ${value}`)}`)
      .join(' ')
    return `wget --method=${info.method} ${headers}${info.body ? ` --body-data=${this.shellQuote(info.body)}` : ''} ${this.shellQuote(info.url)}`
  }

  private static generateFallback(language: string, curlCommand: string): string {
    const label = this.languageLabels[language] || language
    return `# ${label}
# Equivalent cURL request:
${curlCommand}`
  }

  static getSupportedLanguages(): string[] {
    return Object.keys(this.languageMap)
  }

  static getLanguageLabel(language: string): string {
    return this.languageLabels[language] || language
  }

  static getLanguageExtension(language: string): string {
    return this.languageExtensions[language] || 'txt'
  }
}
