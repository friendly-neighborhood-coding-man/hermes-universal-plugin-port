// Synthetic native OpenClaw tool fixture; intentionally has no host dependencies.
export default {
  id: 'openclaw-sample',
  register(api) {
    api.registerTool({
      name: 'reverse_text',
      description: 'Reverse a supplied string without I/O',
      parameters: {type: 'object', properties: {text: {type:'string'}}, required: ['text']},
      async execute(_id, params) {
        return {content: [{type:'text',text: String(params.text).split('').reverse().join('')}]};
      },
    });
  },
};
