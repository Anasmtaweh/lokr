
const User = require('./models/User');
const signup = async (req, res) => {
    const user = new User(req.body);
    await user.save();
};
